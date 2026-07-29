#!/usr/bin/env python3
import json, urllib.parse, urllib.request
H=730
f="armRegionName eq 'westeurope' and contains(productName,'App Service') and contains(skuName,'P2 v3') and type eq 'Consumption' and unitOfMeasure eq '1 Hour'"
u='https://prices.azure.com/api/retail/prices?'+urllib.parse.urlencode({'$filter':f,'currencyCode':'CHF'})
items=json.load(urllib.request.urlopen(u,timeout=60)).get('Items',[])
for i in items[:5]:
    p=i['retailPrice']
    print(i.get('productName'), i.get('skuName'), p, 'CHF/h', '~', round(p*H,2), 'CHF/mo')
