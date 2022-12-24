from flask import render_template, url_for, request, flash, redirect, abort
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

import configurator
import netbox_client
from resolver import DNSConnectionError
from webapp import app
from webapp.forms import ResourceForm, ResourceType
from webapp.models import db, Resource, IP
from webapp.settings import PREFIX, NB_URL, NB_API_TOKEN, NB_CISCO, NB_BRASS_ID, JUNIPER_ROUTERS, username, password


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
    ).join(Resource.ips, isouter=True).group_by(Resource.id)

    input_form = ResourceForm(obj=request.form)

    if request.method == "POST":
        action = request.form.get('action', None)
        back = url_for('resources_view')

        if action == 'add_resource':
            if input_form.validate_on_submit():
                resource = Resource()
                resource.name = input_form.name.data
                resource.resource_type = input_form.resource_type.data
                resource.status = resource.STATUS_ERROR
                resource.order = input_form.order.data
                resource.added_date = input_form.added_date.data
                resource.description = input_form.description.data
                db.session.add(resource)

                try:
                    db.session.commit()
                except IntegrityError:
                    flash('Already exists.', category='error')
                    return redirect(back)

                try:
                    resource.update_ips()
                except DNSConnectionError:
                    flash('DNS is unreachable', category='error')
                else:
                    flash('Resource successfully added', category='success')

                return redirect(back)

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
                resource.name = form.name.data
                resource.resource_type = form.resource_type.data
                resource.order = form.order.data
                resource.added_date = form.added_date.data
                resource.description = form.description.data

                try:
                    db.session.commit()
                except IntegrityError:
                    flash('Already exists.', category='error')
                    return redirect(back)

                try:
                    resource.update_ips()
                except DNSConnectionError:
                    flash('DNS is unreachable', category='error')
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

            return redirect(back)

    return render_template('resource.html', form=form, resource=resource)


@app.route(f'{PREFIX}/config')
def config_view():
    page_title = 'Config'

    nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)
    cisco_hosts = nb.dcim.devices.filter(status='active', role_id=NB_BRASS_ID, manufacturer_id=NB_CISCO)

    juniper_hosts = configurator.get_juniper_hosts(nb, JUNIPER_ROUTERS)

    return render_template('devices.html', page_title=page_title, cisco_hosts=cisco_hosts, juniper_hosts=juniper_hosts)


@app.route(f'{PREFIX}/devices/<hostname>/', methods=['POST', 'GET'])
def device_view(hostname):
    nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)
    cisco_hosts = [
        host for host in nb.dcim.devices.filter(status='active', role_id=NB_BRASS_ID, manufacturer_id=NB_CISCO)
    ]

    juniper_hosts = configurator.get_juniper_hosts(nb, JUNIPER_ROUTERS)

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

        if action == 'diff':
            ips = IP.query.all()
            resolved_ips = set(ip.ip for ip in ips)

            vendor = host.device_type.manufacturer.name.lower()

            diff = configurator.get_diff(
                host=host.primary_ip.address.split('/')[0],
                username=username,
                password=password,
                vendor=vendor,
                resolved_ips=resolved_ips,
            )
            return render_template('device.html', host=host, diff=diff)

        if action == 'generate':
            typed_ips_dict = {}
            for res_type in ResourceType:
                query = db.session.query(IP.ip) \
                    .filter(Resource.resource_type == res_type.name) \
                    .join(Resource, Resource.id == IP.resource_id)
                typed_ips_dict[res_type.name] = sorted(ip.ip for ip in query)

            vendor = host.device_type.manufacturer.name.lower()

            device_config = configurator.generate_config(
                host=host.primary_ip.address.split('/')[0],
                username=username,
                password=password,
                vendor=vendor,
                typed_ips=typed_ips_dict,
            )

            return render_template('device.html', host=host, device_config=device_config)

    return render_template('device.html', host=host)
