import csv, json, io, re, zipfile
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen
from urllib.parse import urljoin
from html.parser import HTMLParser
from pathlib import Path

BASE="https://www.tepco.co.jp/forecast/html/area-download-j.html"
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag=="a":
            href=dict(attrs).get("href")
            if href: self.links.append(href)
def read(url):
    with urlopen(url,timeout=30) as response:
        raw=response.read()
    for enc in ("utf-8-sig","cp932"):
        try: return raw.decode(enc)
        except UnicodeError: pass
    raise ValueError("unknown encoding")
def links(url):
    p=Links(); p.feed(read(url))
    return [urljoin(url,x) for x in p.links]
def collect():
    now=datetime.now(timezone(timedelta(hours=9)))
    target=(now-timedelta(days=1)).date()
    result={"date":str(target),"retrieved_at":now.isoformat(),"status":"failed","source":BASE}
    try:
        pages=[x for x in links(BASE) if str(target.year) in x and (".zip" in x.lower() or ".csv" in x.lower())]
        candidates=[]
        for page in pages:
            candidates.extend([page] if ".csv" in page.lower() or ".zip" in page.lower() else [x for x in links(page) if ".csv" in x.lower()])
        for url in dict.fromkeys(candidates):
            try:
                
                if ".zip" in url.lower():
                    with urlopen(url,timeout=30) as response: raw=response.read()
                    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                        names=[n for n in archive.namelist() if n.lower().endswith(".csv") and target.strftime("%Y%m%d") in n and ("実績" in n or "actual" in n.lower())]
                        if len(names)!=1: continue
                        raw=archive.read(names[0])
                    try: payload=raw.decode("utf-8-sig")
                    except UnicodeError: payload=raw.decode("cp932")
                else: payload=read(url)
                rows=list(csv.reader(io.StringIO(payload)))
                matches=[row for row in rows if len(row)>2 and row[0].strip() in {str(target),f"{target.year}/{target.month}/{target.day}",target.strftime("%Y/%m/%d"),target.strftime("%Y%m%d")}]
                if len(matches)==48 and len({row[1] for row in matches})==48:
                    result.update(status="rows_collected_unverified",source=url,header=rows[:8],rows=matches)
                    break
            except Exception: continue
        if result["status"]=="failed": result["error"]="No CSV with 48 distinct target-date rows found"
    except Exception as e: result["error"]=str(e)
    Path("data").mkdir(exist_ok=True)
    Path("data/tepco_candidate.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": collect()
