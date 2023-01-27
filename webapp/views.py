import logging

from flask import render_template, url_for, request, flash, redirect, abort
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func, or_

import configurator
import netbox_client
from resolver import DNSConnectionError
from webapp import app
from webapp.forms import ResourceForm
from webapp.models import db, Resource, IP
from webapp.settings import PREFIX, NB_URL, NB_API_TOKEN, JUNIPER_ROUTERS, username, password


@app.route(f'{PREFIX}/resources/', methods=['POST', 'GET'])
def resources_view():
    page_title = 'Resources'

    resources = db.session.query(
        Resource.id,
        Resource.name,
        Resource.resource_type,
        Resource.status,
        Resource.order,
        Resource.added_date,
        Resource.resolve_time,
        Resource.description,
        func.count(IP.resource_id)
    ) \
        .join(Resource.ips, isouter=True) \
        .group_by(Resource.id) \
        .order_by(Resource.name)

    input_form = ResourceForm(obj=request.form)

    if request.method == "POST":
        action = request.form.get('action', None)
        back = url_for('resources_view')

        if action == 'add_resource':
            if input_form.validate_on_submit():
                resource = Resource()
                resource.name = input_form.name.data.strip()
                resource.resource_type = input_form.resource_type.data
                resource.status = resource.STATUS_ERROR
                resource.order = input_form.order.data
                resource.added_date = input_form.added_date.data
                resource.description = input_form.description.data
                db.session.add(resource)

                try:
                    db.session.commit()
                except IntegrityError:
                    flash('Already exists', category='error')
                    return redirect(back)

                try:
                    resource.update_ips()
                except DNSConnectionError:
                    flash('DNS is unreachable', category='error')
                except Exception as e:
                    flash('DNS error', category='error')
                    logging.exception(e)
                else:
                    flash('Resource successfully added', category='success')

                return redirect(back)

    search_str = request.args.get('search')
    search = f'%{search_str}%'
    if search_str:
        resources = resources.filter(
            or_(
                Resource.name.like(search),
                Resource.description.like(search),
                Resource.order.like(search),
                Resource.added_date.like(search),
                Resource.resource_type.like(search),
                Resource.resolve_time.like(search),
            )
        )

    return render_template('resources.html', form=input_form, resources=resources, page_title=page_title)


@app.route(f'{PREFIX}/resources/delete/<int:resource_id>', methods=['POST'])
def delete_resource_view(resource_id):
    if request.method == 'POST':
        resource = Resource.query.get(resource_id)

        db.session.delete(resource)
        db.session.commit()
        flash('Deleted successfully', category='success')
        return redirect(url_for('resources_view'))


@app.route(f'{PREFIX}/resources/<int:resource_id>/', methods=['POST', 'GET'])
def resource_view(resource_id):
    resource = Resource.query.get(resource_id)
    form = ResourceForm(obj=resource)

    if request.method == 'POST':
        back = url_for('resource_view', resource_id=resource_id)
        action = request.form.get('action', None)

        if action == 'update_resource':
            if form.validate_on_submit():
                resource.name = form.name.data.strip()
                resource.resource_type = form.resource_type.data
                resource.order = form.order.data
                resource.added_date = form.added_date.data
                resource.description = form.description.data

                try:
                    db.session.commit()
                except IntegrityError:
                    flash('Already exists', category='error')
                    return redirect(back)
                except Exception as e:
                    flash('DB error', category='error')
                    logging.exception(e)
                    return redirect(back)

                try:
                    resource.update_ips()
                except DNSConnectionError:
                    flash('DNS is unreachable', category='error')
                except Exception as e:
                    flash('DNS error', category='error')
                    logging.exception(e)
                else:
                    flash('Resource successfully updated', category='success')

            return redirect(back)

        if action == 'delete_resource':
            db.session.delete(resource)
            db.session.commit()
            flash('Deleted successfully', category='success')

            return redirect(url_for('resources_view'))

        if action == 'resolve_resource':

            try:
                resource.update_ips()
            except DNSConnectionError:
                flash('DNS is unreachable', category='error')
            except Exception as e:
                flash('DNS error', category='error')
                logging.exception(e)
            return redirect(back)

    return render_template('resource.html', form=form, resource=resource)


@app.route(f'{PREFIX}/config')
def config_view():
    page_title = 'Config'
    back = url_for('resources_view')

    nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)
    try:
        cisco_hosts = configurator.get_cisco_hosts(nb)
        juniper_hosts = configurator.get_juniper_hosts(nb, JUNIPER_ROUTERS)
    except configurator.NetboxConnectionError:
        flash('Netbox connection error', category='error')
        return redirect(back)
    except configurator.NetboxDeviceError:
        flash('Hosts not found in Netbox')
        return redirect(back)
    except Exception as e:
        flash('Netbox error')
        logging.exception(e)
        return redirect(back)

    return render_template('devices.html', page_title=page_title, cisco_hosts=cisco_hosts, juniper_hosts=juniper_hosts)


@app.route(f'{PREFIX}/devices/<hostname>/', methods=['POST', 'GET'])
def device_view(hostname):
    nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)
    back = url_for('device_view', hostname=hostname)

    try:
        cisco_hosts = [host for host in configurator.get_cisco_hosts(nb)]
        juniper_hosts = configurator.get_juniper_hosts(nb, JUNIPER_ROUTERS)
    except configurator.NetboxConnectionError:
        flash('Netbox connection error', category='error')
        return redirect(back)
    except configurator.NetboxDeviceError:
        flash('Hosts not found in Netbox')
        return redirect(back)
    except Exception as e:
        flash('Netbox error')
        logging.exception(e)
        return redirect(back)

    allowed_hosts = juniper_hosts + cisco_hosts

    host = None

    for allowed_host in allowed_hosts:
        if hostname == allowed_host.name:
            host = allowed_host
            break

    if not host:
        return abort(404)

    if request.method == 'POST':
        action = request.form.get('action', None)
        back = url_for('device_view', hostname=hostname)

        if action == 'diff':
            ips = IP.query.all()
            resolved_ips = set(ip.ip for ip in ips)

            vendor = host.device_type.manufacturer.name.lower()

            try:
                diff = configurator.get_diff(
                    host=host.primary_ip.address.split('/')[0],
                    username=username,
                    password=password,
                    vendor=vendor,
                    resolved_ips=resolved_ips,
                )
            except configurator.OGAuthenticationException:
                flash('Authentication error', category='error')
                return redirect(back)
            except configurator.OGTimeoutException:
                flash('Timeout error', category='error')
                return redirect(back)
            except Exception as e:
                flash('Device error')
                logging.exception(e)
                return redirect(back)

            return render_template('device.html', host=host, diff=diff)

        if action == 'generate':
            ips = IP.query.all()
            resolved_ips = set(ip.ip for ip in ips)
            resolved_ips = sorted(resolved_ips)

            vendor = host.device_type.manufacturer.name.lower()

            try:
                device_config = configurator.generate_config(
                    host=host.primary_ip.address.split('/')[0],
                    username=username,
                    password=password,
                    vendor=vendor,
                    ips=resolved_ips,
                )
            except configurator.OGAuthenticationException:
                flash('Authentication error', category='error')
                return redirect(back)
            except configurator.OGTimeoutException:
                flash('Timeout error', category='error')
                return redirect(back)
            except Exception as e:
                flash('Device error')
                logging.exception(e)
                return redirect(back)

            return render_template('device.html', host=host, device_config=device_config)

        if action == 'config':
            ips = IP.query.all()
            resolved_ips = set(ip.ip for ip in ips)
            resolved_ips = sorted(resolved_ips)

            vendor = host.device_type.manufacturer.name.lower()

            try:
                device_config = configurator.configure(
                    host=host.primary_ip.address.split('/')[0],
                    username=username,
                    password=password,
                    vendor=vendor,
                    ips=resolved_ips,
                )
            except configurator.OGAuthenticationException:
                flash('Authentication error', category='error')
                return redirect(back)
            except configurator.OGTimeoutException:
                flash('Timeout error', category='error')
                return redirect(back)
            except configurator.OGWriteTimeoutException:
                flash('Timeout while save configuration. Check device', category='error')
                return redirect(back)
            except Exception as e:
                flash('Device error')
                logging.exception(e)
                return redirect(back)

            return render_template('device.html', host=host, device_config=device_config)

    return render_template('device.html', host=host)
