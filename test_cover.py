import time
import requests
import re

r = requests.get('http://127.0.0.1:8900/', timeout=15)
papers = re.findall(r'/cover/([^\"]+)', r.text)
if papers:
    print('Testing cover for:', papers[0])
    t0 = time.time()
    try:
        r2 = requests.get(f'http://127.0.0.1:8900/cover/{papers[0]}', timeout=30)
        print('Cover status:', r2.status_code, 'time:', time.time() - t0)
    except Exception as e:
        print('Cover Error:', e, 'time:', time.time() - t0)
