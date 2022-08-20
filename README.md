## Применение

`python gogen.py resolve`

Отрезолвит domains из файла *og_domains.txt*.
Сети и адреса хостов останутся неизменными.
Запишет результат в файл *og_networks.txt*.

`python gogen.py generate (juniper|cisco)`

Выведет конфиг по определенному вендору. 
Список отрезовленных ip берется из файла *og_networks.txt*.

`python gogen.py config_dev dev_name`

Зальет конфиг на указанный девайс. 
Список отрезовленных ip берется из файла *og_networks.txt*.

`python gogen.py config_all (juniper|cisco)`

Зальет конфиг на все девайсы определенного вендора. 
Список отрезовленных ip берется из файла *og_networks.txt*.
Список девайсов будет взят из Netbox.
