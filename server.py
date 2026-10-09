"""BayFlow demo application: authenticated, shop-scoped workflow API + static UI."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import hashlib, hmac, json, os, secrets, sqlite3, threading, time

ROOT = Path(__file__).parent
env_file = ROOT / '.env'
if env_file.exists():
 for line in env_file.read_text(encoding='utf-8').splitlines():
  line=line.strip()
  if line and not line.startswith('#') and '=' in line:
   key,value=line.split('=',1); os.environ.setdefault(key.strip(),value.strip())
DB = Path(os.environ.get("BAYFLOW_DATABASE", ROOT / "bayflow.sqlite3"))
LOCK = threading.RLock()
ROLES = {"owner", "advisor", "technician", "qc", "parts", "customer"}
NEXT = {
 "PENDING":{"advisor":{"CONFIRMED","CANCELLED"}},
 "CONFIRMED":{"advisor":{"ASSIGNED"}}, "ASSIGNED":{"technician":{"INSPECTING"}},
 "INSPECTING":{"technician":{"ESTIMATE_REVIEW"}}, "ESTIMATE_REVIEW":{"advisor":{"AWAITING_CUSTOMER"}},
 "AWAITING_CUSTOMER":{"customer":{"ESTIMATE_APPROVED","ESTIMATE_REJECTED"}},
 "ESTIMATE_REJECTED":{"advisor":{"ESTIMATE_REVIEW","CANCELLED"}},
 "ESTIMATE_APPROVED":{"advisor":{"PARTS_PENDING"}}, "PARTS_PENDING":{"parts":{"PARTS_ORDERED","PARTS_READY"}},
 "PARTS_ORDERED":{"parts":{"PARTS_READY"}}, "PARTS_READY":{"parts":{"IN_REPAIR"}},
 "IN_REPAIR":{"technician":{"QC_PENDING"}}, "QC_PENDING":{"qc":{"QC_IN_PROGRESS"}},
 "QC_IN_PROGRESS":{"qc":{"READY_FOR_PICKUP","IN_REPAIR"}},
 "READY_FOR_PICKUP":{"advisor":{"COMPLETED"}},
}
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT, phone TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS shops(id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT, city TEXT, address TEXT, phone TEXT, services TEXT, capacity INTEGER DEFAULT 2);
CREATE TABLE IF NOT EXISTS members(user_id INTEGER, shop_id INTEGER, role TEXT, PRIMARY KEY(user_id,shop_id));
CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, shop_id INTEGER, sku TEXT, name TEXT, qty INTEGER, reorder INTEGER, cost INTEGER);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, shop_id INTEGER, customer_id INTEGER, service TEXT, notes TEXT, plate TEXT, vehicle TEXT, slot TEXT, status TEXT, tech_id INTEGER, parts_id INTEGER, qc_id INTEGER, estimate TEXT DEFAULT '[]', revision INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, booking_id INTEGER, actor TEXT, old TEXT, new TEXT, note TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER, message TEXT, booking_id INTEGER, read INTEGER DEFAULT 0, at TEXT);
CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, booking_id INTEGER, title TEXT, description TEXT, resolved INTEGER DEFAULT 0, at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, expires INTEGER);
"""
def db():
 DB.parent.mkdir(parents=True, exist_ok=True)
 c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def pw(s): return hashlib.pbkdf2_hmac('sha256',s.encode(),os.environ.get('BAYFLOW_PASSWORD_PEPPER','local-demo-pepper-change-for-deployment').encode(),160000).hex()
def seed():
 with LOCK, db() as c:
  c.executescript(SCHEMA)
  if c.execute('select count(*) from shops').fetchone()[0]: return
  people=[('Fatima Raza','owner@bayflow.demo','Bayflow2026!','owner'),('Bilal Ahmed','advisor@bayflow.demo','Bayflow2026!','advisor'),('Imran Khan','tech@bayflow.demo','Bayflow2026!','technician'),('Sara Malik','qc@bayflow.demo','Bayflow2026!','qc'),('Usman Ali','parts@bayflow.demo','Bayflow2026!','parts'),('Ahmed Customer','customer@bayflow.demo','Bayflow2026!','customer')]
  ids={}
  for n,e,p,r in people:
   cur=c.execute('insert into users(name,email,password,role) values(?,?,?,?)',(n,e,pw(p),r)); ids[r]=cur.lastrowid
  shops=[('Lahore Auto Care','Lahore','Gulberg III, Lahore','0300 1234567','Oil change,Check engine,Brakes,Tire rotation'),('Karachi Motor Works','Karachi','PECHS, Karachi','0300 7654321','Oil change,Brakes,Diagnostics,AC service'),('Islamabad Car Clinic','Islamabad','F-10 Markaz, Islamabad','0300 9876543','Diagnostics,Tire rotation,AC service,Brakes')]
  for name,city,address,phone,services in shops:
   cur=c.execute('insert into shops(owner_id,name,city,address,phone,services) values(?,?,?,?,?,?)',(ids['owner'],name,city,address,phone,services)); sid=cur.lastrowid
   for role in ('advisor','technician','qc','parts'): c.execute('insert into members values(?,?,?)',(ids[role],sid,role))
   for sku,n,q,cost in [('OIL-5W30','Engine oil 5W-30',18,1300),('FILTER-01','Oil filter',12,900),('COIL-01','Ignition coil',0,6500),('PAD-SET','Brake pad set',5,8500)]: c.execute('insert into inventory(shop_id,sku,name,qty,reorder,cost) values(?,?,?,?,?,?)',(sid,sku,n,q,4,cost))
  sid=1
  cur=c.execute("insert into bookings(shop_id,customer_id,service,notes,plate,vehicle,slot,status,tech_id,parts_id,created) values(?,?,?,?,?,?,?,?,?,?,?)",(sid,ids['customer'],'Check engine, Oil change','Engine light on; vibration at idle','LEA-1234','2016 Honda Civic','2026-10-12 10:00','PENDING',None,None,time.strftime('%Y-%m-%d %H:%M'))); bid=cur.lastrowid
  c.execute('insert into history(booking_id,actor,old,new,note,at) values(?,?,?,?,?,?)',(bid,'Customer','', 'PENDING','Online booking created',time.strftime('%Y-%m-%d %H:%M')))
  c.execute('insert into notifications(user_id,message,booking_id,at) values(?,?,?,?)',(ids['advisor'],'New booking: LEA-1234 • Check engine',bid,time.strftime('%Y-%m-%d %H:%M')))

class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
 def log_message(self,*a): pass
 def sendj(self,obj,status=200):
  data=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.send_header('Access-Control-Allow-Origin','same-origin'); self.end_headers(); self.wfile.write(data)
 def body(self):
  try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
  except: return {}
 def user(self,c):
  tok=self.headers.get('Authorization','').replace('Bearer ','')
  row=c.execute('select u.*,s.expires from sessions s join users u on u.id=s.user_id where s.token=?',(tok,)).fetchone()
  if not row or row['expires']<time.time(): return None
  return row
 def do_OPTIONS(self): self.send_response(204); self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type'); self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,OPTIONS'); self.end_headers()
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/shops':
   with db() as c: self.sendj([dict(r,services=r['services'].split(',')) for r in c.execute('select id,name,city,address,phone,services from shops')]); return
  if not path.startswith('/api/'): return super().do_GET()
  with db() as c:
   u=self.user(c)
   if not u: self.sendj({'error':'Please sign in to continue.'},401); return
   if path=='/api/me': self.sendj({'id':u['id'],'name':u['name'],'email':u['email'],'role':u['role']}); return
   if path=='/api/data':
    role=u['role']; shops=c.execute('select s.* from shops s left join members m on m.shop_id=s.id where s.owner_id=? or m.user_id=?',(u['id'],u['id'])).fetchall()
    if role=='customer':
     rows=c.execute('select b.*,s.name shop_name,s.city from bookings b join shops s on s.id=b.shop_id where customer_id=? order by b.id desc',(u['id'],)).fetchall()
    else:
     sid=int(self.headers.get('X-Shop-Id') or (shops[0]['id'] if shops else 0)); allowed=c.execute('select 1 from shops s left join members m on m.shop_id=s.id where s.id=? and (s.owner_id=? or m.user_id=?)',(sid,u['id'],u['id'])).fetchone()
     if not allowed: self.sendj({'error':'Shop access denied.'},403); return
     query='select b.*,u.name customer_name,u.email customer_email from bookings b join users u on u.id=b.customer_id where b.shop_id=?'
     args=[sid]
     if role=='technician': query+=' and b.tech_id=?'; args.append(u['id'])
     if role=='qc': query+=" and b.status in ('QC_PENDING','QC_IN_PROGRESS')"
     rows=c.execute(query+' order by b.id desc',args).fetchall()
    output=[]
    for r in rows:
     d=dict(r); d['estimate']=json.loads(d.get('estimate') or '[]'); d['history']=[dict(h) for h in c.execute('select * from history where booking_id=? order by id',(r['id'],))]; d['issues']=[dict(i) for i in c.execute('select * from issues where booking_id=? order by id desc',(r['id'],))]; output.append(d)
    sid=(shops[0]['id'] if shops else None)
    if role!='customer' and self.headers.get('X-Shop-Id'): sid=int(self.headers['X-Shop-Id'])
    inv=c.execute('select * from inventory where shop_id=?',(sid,)).fetchall() if sid else []
    team=c.execute('select u.id,u.name,u.email,m.role from members m join users u on u.id=m.user_id where m.shop_id=?',(sid,)).fetchall() if sid else []
    notes=c.execute('select * from notifications where user_id=? order by id desc limit 20',(u['id'],)).fetchall()
    self.sendj({'user':{'id':u['id'],'name':u['name'],'email':u['email'],'role':role},'shops':[dict(x,services=x['services'].split(',')) for x in shops], 'bookings':output,'inventory':[dict(x) for x in inv],'team':[dict(x) for x in team],'notifications':[dict(x) for x in notes]}); return
   self.sendj({'error':'Not found'},404)
 def do_POST(self):
  path=urlparse(self.path).path; data=self.body()
  with LOCK, db() as c:
   if path=='/api/login':
    row=c.execute('select * from users where lower(email)=lower(?)',(data.get('email',''),)).fetchone()
    if not row or not hmac.compare_digest(row['password'],pw(data.get('password',''))): self.sendj({'error':'Email ya password durust nahi.'},401); return
    token=secrets.token_urlsafe(36); c.execute('insert into sessions values(?,?,?)',(token,row['id'],time.time()+86400*7)); self.sendj({'token':token}); return
   if path=='/api/bookings':
    u=self.user(c)
    if not u or u['role']!='customer': self.sendj({'error':'Customer sign in required.'},403); return
    sid=int(data.get('shop_id',0)); shop=c.execute('select * from shops where id=?',(sid,)).fetchone()
    if not shop: self.sendj({'error':'Shop not found'},404); return
    slot=data.get('slot',''); count=c.execute('select count(*) from bookings where shop_id=? and slot=? and status not in (\'CANCELLED\',\'COMPLETED\')',(sid,slot)).fetchone()[0]
    if count>=shop['capacity']: self.sendj({'error':'This time is full. Please choose another slot.'},409); return
    cur=c.execute("insert into bookings(shop_id,customer_id,service,notes,plate,vehicle,slot,status,created) values(?,?,?,?,?,?,?,'PENDING',?)",(sid,u['id'],', '.join(data.get('services',[])),data.get('notes',''),data.get('plate',''),data.get('vehicle',''),slot,time.strftime('%Y-%m-%d %H:%M'))); bid=cur.lastrowid
    c.execute('insert into history(booking_id,actor,old,new,note,at) values(?,?,?,?,?,?)',(bid,u['name'],'','PENDING','Booking submitted',time.strftime('%Y-%m-%d %H:%M')))
    for m in c.execute("select user_id from members where shop_id=? and role='advisor'",(sid,)): c.execute('insert into notifications(user_id,message,booking_id,at) values(?,?,?,?)',(m['user_id'],'New customer booking received',bid,time.strftime('%Y-%m-%d %H:%M')))
    self.sendj({'id':bid,'status':'PENDING'},201); return
   if path=='/api/register':
    name=data.get('name','').strip(); email=data.get('email','').strip().lower(); password=data.get('password','')
    if not name or '@' not in email or len(password)<8: self.sendj({'error':'Enter your name, a valid email, and a password of at least 8 characters.'},400); return
    if c.execute('select 1 from users where email=?',(email,)).fetchone(): self.sendj({'error':'That email already has an account. Please sign in.'},409); return
    cur=c.execute("insert into users(name,email,password,role) values(?,?,?,'customer')",(name,email,pw(password))); token=secrets.token_urlsafe(36); c.execute('insert into sessions values(?,?,?)',(token,cur.lastrowid,time.time()+86400*7)); self.sendj({'token':token},201); return
   u=self.user(c)
   if not u: self.sendj({'error':'Please sign in.'},401); return
   if path=='/api/shops' and u['role']=='owner':
    cur=c.execute('insert into shops(owner_id,name,city,address,phone,services) values(?,?,?,?,?,?)',(u['id'],data.get('name'),data.get('city'),data.get('address'),data.get('phone'),','.join(data.get('services',[])))); self.sendj({'id':cur.lastrowid},201); return
   if path=='/api/team' and u['role']=='owner':
    name=data.get('name','').strip(); email=data.get('email','').strip().lower(); role=data.get('role'); password=data.get('password',''); sid=int(data.get('shop_id',0))
    if role not in ('advisor','technician','qc','parts') or len(password)<8 or not name or '@' not in email: self.sendj({'error':'Enter valid team details, choose a role and use a password of at least 8 characters.'},400); return
    if not c.execute('select 1 from shops where id=? and owner_id=?',(sid,u['id'])).fetchone(): self.sendj({'error':'Shop access denied.'},403); return
    found=c.execute('select id from users where email=?',(email,)).fetchone()
    if found:
     uid=found['id']; existing=c.execute('select role from users where id=?',(uid,)).fetchone()['role']
     if existing=='customer': self.sendj({'error':'This email belongs to a customer account.'},409); return
    else: uid=c.execute('insert into users(name,email,password,role) values(?,?,?,?)',(name,email,pw(password),role)).lastrowid
    c.execute('insert or replace into members(user_id,shop_id,role) values(?,?,?)',(uid,sid,role)); self.sendj({'ok':True},201); return
   parts=path.strip('/').split('/')
   if len(parts)==3 and parts[0]=='api' and parts[1]=='bookings':
    bid=int(parts[2]); b=c.execute('select * from bookings where id=?',(bid,)).fetchone()
    if not b or u['role']=='customer' and b['customer_id']!=u['id']: self.sendj({'error':'Booking access denied.'},403); return
    sid=b['shop_id']; member=c.execute('select role from members where shop_id=? and user_id=?',(sid,u['id'])).fetchone(); role='owner' if c.execute('select 1 from shops where id=? and owner_id=?',(sid,u['id'])).fetchone() else (member['role'] if member else u['role'] if u['role']=='customer' else None)
    action=data.get('action')
    if action=='estimate':
     if role not in ('technician','advisor','owner') or role=='technician' and b['tech_id']!=u['id']: self.sendj({'error':'Only the assigned technician can submit an estimate.'},403); return
     c.execute('update bookings set estimate=?,revision=revision+1,status=? where id=?',(json.dumps(data.get('items',[])), 'ESTIMATE_REVIEW' if role=='technician' else b['status'],bid));
     if role=='technician': self.notify(c,bid,sid,'advisor','Technician submitted an estimate for review')
     self.sendj({'ok':True}); return
    if action=='assign':
     if role not in ('advisor','owner'): self.sendj({'error':'Advisor access required.'},403); return
     target=data.get('role'); uid=int(data.get('user_id',0)); mem=c.execute('select 1 from members where shop_id=? and user_id=? and role=?',(sid,uid,target)).fetchone()
     if target not in ('technician','parts') or not mem: self.sendj({'error':'Choose a team member from this shop.'},400); return
     col='tech_id' if target=='technician' else 'parts_id'; c.execute(f'update bookings set {col}=? where id=?',(uid,bid)); self.sendj({'ok':True}); return
    if action=='issue':
     if role not in ('qc','owner'): self.sendj({'error':'QC access required.'},403); return
     c.execute('insert into issues(booking_id,title,description,at) values(?,?,?,?)',(bid,data.get('title'),data.get('description'),time.strftime('%Y-%m-%d %H:%M'))); self.transition(c,u,b,'IN_REPAIR',data.get('title','QC issue')); self.sendj({'ok':True}); return
    target=data.get('status')
    allowed=target in NEXT.get(b['status'],{}).get(role,set()) or role=='owner' or (target=='CANCELLED' and role in ('advisor','customer') and b['status'] not in ('IN_REPAIR','QC_PENDING','QC_IN_PROGRESS','READY_FOR_PICKUP','COMPLETED','CANCELLED'))
    if not target or not allowed: self.sendj({'error':f'{role or "This role"} cannot move this booking from {b["status"]} to {target}.'},403); return
    if role=='technician' and b['tech_id']!=u['id']: self.sendj({'error':'This job is assigned to another technician.'},403); return
    if target=='ASSIGNED':
     uid=int(data.get('user_id') or b['tech_id'] or 0); mem=c.execute("select 1 from members where shop_id=? and user_id=? and role='technician'",(sid,uid)).fetchone()
     if not mem: self.sendj({'error':'Choose a technician from this shop.'},400); return
     c.execute('update bookings set tech_id=? where id=?',(uid,bid))
    if target=='IN_REPAIR' and b['status']=='PARTS_READY':
     for item in json.loads(b['estimate'] or '[]'):
      match=c.execute('select id,qty from inventory where shop_id=? and lower(name) like ?', (sid,'%'+item.get('name','').lower()+'%')).fetchone()
      if match and match['qty']<int(item.get('qty',1)): self.sendj({'error':f'Not enough stock for {item.get("name")}. Receive parts before allocating.'},409); return
      if match: c.execute('update inventory set qty=qty-? where id=?',(int(item.get('qty',1)),match['id']))
    self.transition(c,u,b,target,data.get('note','')); self.sendj({'ok':True}); return
   if path=='/api/inventory/receive':
    if u['role'] not in ('parts','owner'): self.sendj({'error':'Parts role required.'},403); return
    sid=int(data.get('shop_id',0)); member=c.execute("select 1 from members where shop_id=? and user_id=? and role='parts'",(sid,u['id'])).fetchone(); owner=c.execute('select 1 from shops where id=? and owner_id=?',(sid,u['id'])).fetchone()
    if not member and not owner: self.sendj({'error':'Shop access denied.'},403); return
    c.execute('update inventory set qty=qty+? where id=? and shop_id=?',(max(1,int(data.get('quantity',1))),int(data.get('item_id',0)),sid)); self.sendj({'ok':True}); return
   self.sendj({'error':'Not found'},404)
 def notify(self,c,bid,sid,role,msg):
  for r in c.execute('select user_id from members where shop_id=? and role=?',(sid,role)): c.execute('insert into notifications(user_id,message,booking_id,at) values(?,?,?,?)',(r['user_id'],msg,bid,time.strftime('%Y-%m-%d %H:%M')))
 def transition(self,c,u,b,target,note):
  c.execute('update bookings set status=? where id=?',(target,b['id'])); c.execute('insert into history(booking_id,actor,old,new,note,at) values(?,?,?,?,?,?)',(b['id'],u['name'],b['status'],target,note,time.strftime('%Y-%m-%d %H:%M')))
  role={'PENDING':'advisor','ESTIMATE_REVIEW':'advisor','AWAITING_CUSTOMER':'customer','ESTIMATE_APPROVED':'advisor','PARTS_PENDING':'parts','PARTS_ORDERED':'parts','PARTS_READY':'technician','QC_PENDING':'qc','IN_REPAIR':'technician','READY_FOR_PICKUP':'customer','ESTIMATE_REJECTED':'advisor','COMPLETED':'customer'}.get(target)
  if role=='customer': ids=[b['customer_id']]
  elif role: ids=[x['user_id'] for x in c.execute('select user_id from members where shop_id=? and role=?',(b['shop_id'],role))]
  else: ids=[]
  for uid in ids: c.execute('insert into notifications(user_id,message,booking_id,at) values(?,?,?,?)',(uid,f'Booking #{b["id"]}: {target.replace("_"," ")}',b['id'],time.strftime('%Y-%m-%d %H:%M')))

if __name__=='__main__':
 seed(); port=int(os.environ.get('PORT','8000')); print(f'Malika running at http://localhost:{port}'); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
