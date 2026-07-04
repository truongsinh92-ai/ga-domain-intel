#!/usr/bin/env python3
"""
GA Domain Intelligence - Local Proxy Server
Chay: python server.py  HOAC  double-click start.bat
Mo trinh duyet tai: http://localhost:8765
"""

import http.server
import urllib.request
import urllib.error
import json
import os
import re
import base64
import threading
import webbrowser

PORT = int(os.environ.get('PORT', 8765))
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
DFS_BASE = 'https://api.dataforseo.com/v3'

# DataForSEO credentials (internal tool - local only)
DFS_LOGIN = 'truongsinh92@gmail.com'
DFS_PASSWORD = 'b39820618b9f19cf'
DFS_AUTH = base64.b64encode(f'{DFS_LOGIN}:{DFS_PASSWORD}'.encode()).decode()


def dfs_post(path, body):
    """POST to DataForSEO API, return parsed JSON or None on error."""
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        f'{DFS_BASE}{path}',
        data=data,
        headers={
            'Authorization': f'Basic {DFS_AUTH}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f'[DFS] Error {path}: {e}')
        return None


def fetch_similarweb(domain):
    """SimilarWeb public data endpoint (free tier, no auth needed)."""
    url = f'https://data.similarweb.com/api/v1/data?domain={domain}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.similarweb.com/'
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f'[SW] Error: {e}')
        return None


def fetch_traffic(domain):
    """DataForSEO Traffic Analytics - domain overview."""
    r = dfs_post('/traffic_analytics/domain_overview/live', [{'target': domain}])
    if not r:
        return None
    try:
        item = r['tasks'][0]['result'][0]
        return item
    except Exception:
        return None


def fetch_keywords(domain):
    """DataForSEO Traffic Analytics - top keywords."""
    r = dfs_post('/traffic_analytics/domain_keywords/live', [
        {'target': domain, 'limit': 8, 'order_by': ['etv,desc']}
    ])
    if not r:
        return None
    try:
        return r['tasks'][0]['result']
    except Exception:
        return None


def fetch_whois(domain):
    """DataForSEO WHOIS."""
    r = dfs_post('/domain_analytics/whois/overview/live', [{'domain': domain}])
    if not r:
        return None
    try:
        return r['tasks'][0]['result'][0]
    except Exception:
        return None


def build_result_from_sw(domain, sw, keywords_dfs, whois_dfs, claude_company):
    """Map SimilarWeb free data into app format."""
    # SimilarWeb free API response fields
    visits = sw.get('EstimatedMonthlyVisits', {})
    # Get latest month
    monthly = 0
    if visits:
        latest_key = sorted(visits.keys())[-1] if visits else None
        monthly = visits.get(latest_key, 0) if latest_key else 0

    monthly_str = f"~{monthly:,.0f}/tháng" if monthly else 'N/A'

    global_rank = sw.get('GlobalRank', {}).get('Rank', None)
    global_rank_str = f"#{global_rank:,}" if global_rank else 'Không xác định'

    country_rank_data = sw.get('CountryRank', {})
    country_rank = country_rank_data.get('Rank', None)
    country = country_rank_data.get('CountryCode', 'VN')
    country_rank_str = f"{country} #{country_rank:,}" if country_rank else 'Không xác định'

    bounce = sw.get('Engagments', {}).get('BounceRate', None)
    bounce_str = f"{round(bounce * 100, 1)}%" if bounce else 'N/A'

    ppv = sw.get('Engagments', {}).get('PagePerVisit', None)
    ppv_str = f"~{round(ppv, 1)}" if ppv else 'N/A'

    dur = sw.get('Engagments', {}).get('TimeOnSite', None)
    if dur:
        dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}"
    else:
        dur_str = 'N/A'

    # Traffic sources
    sources = []
    ts = sw.get('TrafficSources', {})
    name_map = {
        'Direct': 'direct', 'Search': 'organic_search',
        'Social': 'social', 'Referrals': 'referral',
        'Mail': 'email', 'Paid Referrals': 'paid_search'
    }
    for k, v in ts.items():
        sources.append({'name': name_map.get(k, k.lower()), 'pct': round(v * 100)})

    # Top keywords from SimilarWeb
    kw_list = []
    sw_keywords = sw.get('TopKeywords', [])
    if sw_keywords:
        max_vol = max((k.get('EstimatedValue', 1) for k in sw_keywords), default=1)
        for k in sw_keywords[:8]:
            vol = k.get('EstimatedValue', 0)
            kw_list.append({
                'kw': k.get('Name', ''),
                'vol': f"~{round(vol):,}/tháng",
                'bar': round(vol / max_vol * 100) if max_vol else 0
            })
    elif keywords_dfs:
        max_etv = max((k.get('etv', 1) for k in keywords_dfs), default=1)
        for k in keywords_dfs[:8]:
            etv = k.get('etv', 0)
            kw_list.append({
                'kw': k.get('keyword', ''),
                'vol': f"~{round(etv):,}/tháng",
                'bar': round(etv / max_etv * 100) if max_etv else 0
            })
    if not kw_list:
        kw_list = [{'kw': 'N/A', 'vol': 'N/A', 'bar': 0}]

    # Ads
    paid_pct = ts.get('Paid Referrals', 0)
    ads = {
        'running': paid_pct > 0.01,
        'platforms': ['Google Ads'] if paid_pct > 0.01 else [],
        'note': f"Paid search ~{round(paid_pct*100)}% traffic" if paid_pct > 0.01 else 'Không phát hiện quảng cáo trả phí.'
    }

    # WHOIS
    whois_data = {'registrar': 'N/A', 'created': 'N/A', 'expires': 'N/A', 'tech_stack': []}
    if whois_dfs:
        whois_data['registrar'] = whois_dfs.get('registrar', 'N/A') or 'N/A'
        whois_data['created'] = whois_dfs.get('creation_date', 'N/A') or 'N/A'
        whois_data['expires'] = whois_dfs.get('expiration_date', 'N/A') or 'N/A'

    company = claude_company or {
        'name': domain, 'industry': 'N/A', 'founded_year': 'N/A',
        'domain_created': 'N/A', 'employees': 'N/A', 'hq': 'N/A',
        'description': 'Không có thông tin.'
    }

    return {
        'overview': {
            'monthly_visits': monthly_str,
            'global_rank': global_rank_str,
            'country': country,
            'country_rank': country_rank_str,
            'bounce_rate': bounce_str,
            'pages_per_visit': ppv_str,
            'avg_duration': dur_str
        },
        'traffic_sources': sources if sources else [
            {'name': 'direct', 'pct': 40}, {'name': 'organic_search', 'pct': 35},
            {'name': 'social', 'pct': 15}, {'name': 'referral', 'pct': 10}
        ],
        'keywords': kw_list,
        'ads': ads,
        'company': company,
        'whois': whois_data,
        'confidence': 'high'
    }


def build_result(domain, traffic, keywords, whois, claude_company):
    """Map DataForSEO data + Claude company info into app format."""
    # --- Overview ---
    if traffic:
        mv = traffic.get('visits', None)
        monthly = f"~{mv:,}/tháng" if mv else 'N/A'
        gr = traffic.get('rank', None)
        global_rank = f"#{gr:,}" if gr else 'Không xác định'
        bounce = traffic.get('bounce_rate', None)
        bounce_str = f"{round(bounce*100)}%" if bounce else 'N/A'
        ppv = traffic.get('pages_per_visit', None)
        ppv_str = f"~{round(ppv,1)}" if ppv else 'N/A'
        dur = traffic.get('avg_visit_duration', None)
        dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur else 'N/A'
        confidence = 'high'
    else:
        monthly = 'N/A'; global_rank = 'N/A'; bounce_str = 'N/A'
        ppv_str = 'N/A'; dur_str = 'N/A'; confidence = 'low'

    # --- Traffic sources ---
    sources = []
    if traffic and traffic.get('traffic_sources'):
        ts = traffic['traffic_sources']
        name_map = {
            'direct': 'direct', 'organic': 'organic_search',
            'referral': 'referral', 'social': 'social',
            'paid': 'paid_search', 'mail': 'email'
        }
        for k, v in ts.items():
            sources.append({'name': name_map.get(k, k), 'pct': round(v * 100)})
    if not sources:
        sources = [
            {'name': 'direct', 'pct': 40},
            {'name': 'organic_search', 'pct': 35},
            {'name': 'social', 'pct': 15},
            {'name': 'referral', 'pct': 10}
        ]

    # --- Keywords ---
    kw_list = []
    if keywords:
        max_etv = max((k.get('etv', 1) for k in keywords), default=1)
        for k in keywords[:8]:
            etv = k.get('etv', 0)
            kw_list.append({
                'kw': k.get('keyword', ''),
                'vol': f"~{round(etv):,}/tháng",
                'bar': round(etv / max_etv * 100) if max_etv else 0
            })
    if not kw_list:
        kw_list = [{'kw': 'N/A', 'vol': 'N/A', 'bar': 0}]

    # --- WHOIS ---
    whois_data = {'registrar': 'N/A', 'created': 'N/A', 'expires': 'N/A', 'tech_stack': []}
    if whois:
        whois_data['registrar'] = whois.get('registrar', 'N/A') or 'N/A'
        whois_data['created'] = whois.get('creation_date', 'N/A') or 'N/A'
        whois_data['expires'] = whois.get('expiration_date', 'N/A') or 'N/A'
        ns = whois.get('name_servers', [])
        if ns:
            whois_data['tech_stack'] = ns[:3]

    # --- Company (from Claude) ---
    company = claude_company or {
        'name': domain, 'industry': 'N/A', 'founded_year': 'N/A',
        'domain_created': 'N/A', 'employees': 'N/A', 'hq': 'N/A',
        'description': 'Không có thông tin.'
    }

    # --- Ads (estimate from traffic) ---
    paid_pct = 0
    if traffic and traffic.get('traffic_sources'):
        paid_pct = traffic['traffic_sources'].get('paid', 0)
    ads = {
        'running': paid_pct > 0.01,
        'platforms': ['Google Ads'] if paid_pct > 0.01 else [],
        'note': f"Paid search chiếm ~{round(paid_pct*100)}% traffic" if paid_pct > 0.01 else 'Không phát hiện quảng cáo trả phí.'
    }

    return {
        'overview': {
            'monthly_visits': monthly,
            'global_rank': global_rank,
            'country': 'VN',
            'country_rank': 'N/A',
            'bounce_rate': bounce_str,
            'pages_per_visit': ppv_str,
            'avg_duration': dur_str
        },
        'traffic_sources': sources,
        'keywords': kw_list,
        'ads': ads,
        'company': company,
        'whois': whois_data,
        'confidence': confidence
    }


def get_company_from_claude(domain, api_key):
    """Ask Claude only for company/business info."""
    prompt = f"""Domain: {domain}
Tra ve JSON (KHONG markdown, KHONG backtick):
{{"name":"Ten cong ty","industry":"Nganh nghe","founded_year":"Nam thanh lap","domain_created":"Nam tao domain","employees":"Quy mo nhan su","hq":"Tru so chinh","description":"Mo ta 2-3 cau"}}
Chi dien nhung gi chac chan biet. Neu khong biet dung "N/A"."""

    body = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 400,
        'messages': [{'role': 'user', 'content': prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        ANTHROPIC_URL, data=body,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        text = result.get('content', [{}])[0].get('text', '')
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        print(f'[Claude] Error: {e}')
    return None


class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[GA Intel] {args[0]} {args[1]}")

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        filepath = os.path.join(os.path.dirname(__file__), 'index.html')
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self._cors()
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'index.html not found')

    def do_POST(self):
        if self.path != '/analyze':
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except Exception:
            self._json_error(400, 'Invalid JSON body')
            return

        domain = payload.get('domain', '').strip()
        api_key = payload.get('api_key', '').strip()

        if not domain:
            self._json_error(400, 'Thieu domain')
            return
        if not api_key:
            self._json_error(400, 'Thieu API key')
            return

        print(f'[GA Intel] Phan tich: {domain}')

        # 1. Try SimilarWeb first (free, no auth)
        sw = fetch_similarweb(domain)
        print(f'[GA Intel] SimilarWeb: {"OK" if sw else "N/A"}')

        # 2. DataForSEO as backup for keywords/whois
        keywords_raw = fetch_keywords(domain)
        whois = fetch_whois(domain)

        # 3. Claude for company info only
        company = get_company_from_claude(domain, api_key)

        if sw:
            result = build_result_from_sw(domain, sw, keywords_raw, whois, company)
        else:
            traffic = fetch_traffic(domain)
            result = build_result(domain, traffic, keywords_raw, whois, company)

        self._json_ok(result)

    def _json_ok(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        body = json.dumps({'error': msg}, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    is_cloud = os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT')
    host = '0.0.0.0' if is_cloud else 'localhost'
    server = http.server.HTTPServer((host, PORT), ProxyHandler)
    url = f'http://localhost:{PORT}'
    print(f"\n{'='*50}")
    print(f"  GA Domain Intelligence")
    print(f"  Dang chay tai: {url}")
    print(f"  DataForSEO: {DFS_LOGIN}")
    print(f"  Nhan Ctrl+C de dung")
    print(f"{'='*50}\n")
    if not is_cloud:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer da dung.")
