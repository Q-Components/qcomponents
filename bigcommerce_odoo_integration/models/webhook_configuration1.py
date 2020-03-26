
import requests, json
import logging

_logger = logging.getLogger(__name__)

#store_hash = 'mlrs21vpva'
#client_id = '4cz3hulfs99zaapr8gj2b0pxjwkm0zk'
#token = '9a0ut9phri17smkmvjq7sxut0fqzxed'
#url = 'https://api.bigcommerce.com/stores/'
#version = 'v2'
#webhook_url = 'https://www.ucaraspa.com.sg/update/bigcommerce/quantity'
store_hash = 'scngfdc6ee'
client_id = 'ogj7mmrri390dgadtjttdlv9tl1zmqo'
token = 'fx2fwi46aeaeb3i3y3bupzhb9hpkrs7'
url = 'https://api.bigcommerce.com/stores/'
version = 'v2'
webhook_url = 'https://www.ucaraspa.com.sg/update/bigcommerce/quantity'


data = {
	"scope": "store/product/inventory/updated",
	"destination": webhook_url,
	"is_active": True
}

headers = {
    'accept': "application/json",
    'content-type': "application/json",
    'x-auth-client': client_id,
    'x-auth-token': token,
}

conn = requests.post(url=(url+store_hash+'/'+version+'/hooks'), headers=headers, data=json.dumps(data))
_logger.warning('>>>>>>>>>>>>>>> \n \n \n connection >>>>>>>%s'%(conn.text))
