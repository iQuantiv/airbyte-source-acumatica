import requests
import json
import httplib2

config={
    "BASEURL": "https://mainedrillingandblasting.acumatica.com",
    "CLIENTID": "C0625E9C-959E-24D1-08C6-245D1A14DFD4@MDB-UserTesting",
    "CLIENTSECRET":"HY5XGtaPxGUwKiUhqiJMLw",
    "USERNAME": "MDBANALYTICS",
    "PASSWORD": "0kX&jkex7Agn%xMW"}

def get_access_token():
    client_id = config["CLIENTID"]
    client_secret = config["CLIENTSECRET"]
    username = config["USERNAME"]
    password = config["PASSWORD"]
    scope = 'api offline_access'
    grant_type = 'password'
    token_url = f'{config["BASEURL"]}/identity/connect/token'
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': grant_type,
        'username': username,
        'password': password,
        'scope': scope
    }
    
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        token = response.json()['access_token']
        print("Access token obtained successfully!")
        return token
    else:
        raise Exception(f"Failed to obtain access token: {response.status_code}, {response.text}")



url = "https://mainedrillingandblasting.acumatica.com/entity/Default/23.200.001/SalesOrder"#?%24filter=LastModified+gt+datetimeoffset%272024-08-26T14%3A46%3A33.597%2B00%3A00%27"

payload = {}
headers= {#'User-Agent': 'python-requests/2.32.3'
           'Accept-Encoding': 'gzip, deflate, br'
          , 'Accept': 'application/json'
          , 'Connection': 'Close'
          , 'Content-Type': 'application/json'
          , 'Cache-Control': 'no-cache'
          , 'Cookie': 'ASP.NET_SessionId=04ifihpqvzvielnivxkrovyv; CompanyID=MDB-UserTesting; Locale=Culture=en-US&TimeZone=GMTM0500G; UserBranch=5; __RequestVerificationToken=Zjx2rWbq9zwmcTr3r74v1cBBNlgFxUjVwYBECFGtEkP60Y56JeFw6Zlh_Chl8i7IscCm2HXtqyC1Yr13ZPEZuhqrrXw1'
          , 'Authorization': f'Bearer {get_access_token()}'}


response = requests.request("GET", url, headers=headers)
print(response)
#print(response.text)
if(len(response.text)>0):
    responsearray=json.loads(response.text)
    print(f'Length of response:{len(responsearray)}')
else:
    print("No records returned")

logoutresponse=requests.request("POST", f'{config["BASEURL"]}/entity/auth/logout', headers=headers, data=payload)

print(logoutresponse)