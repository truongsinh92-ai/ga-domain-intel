/** GA YouTube Uploader - Golden Arch (@GoldenArch-kts)
 *  Doc queue.json tren GitHub, tu dang video moi len kenh YouTube Golden Arch.
 *  Claude cap nhat queue; script chay moi gio.
 *  Cai dat 1 lan: Script properties CLIENT_ID, CLIENT_SECRET -> chay authUrl() -> mo link, chon kenh Golden Arch.
 */
var GA_CHANNEL = 'UCvN-t-k6m5QfDVmT5APLtUw'; // chi dang len kenh Golden Arch
var BASE = 'https://raw.githubusercontent.com/truongsinh92-ai/ga-domain-intel/ga-media/';

function getService_() {
  var p = PropertiesService.getScriptProperties();
  return OAuth2.createService('youtube')
    .setAuthorizationBaseUrl('https://accounts.google.com/o/oauth2/v2/auth')
    .setTokenUrl('https://oauth2.googleapis.com/token')
    .setClientId(p.getProperty('CLIENT_ID'))
    .setClientSecret(p.getProperty('CLIENT_SECRET'))
    .setCallbackFunction('authCallback')
    .setPropertyStore(p)
    .setScope('https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube')
    .setParam('access_type', 'offline')
    .setParam('prompt', 'consent');
}

function authUrl() {
  var url = getService_().getAuthorizationUrl();
  PropertiesService.getScriptProperties().setProperty('authUrl', url);
  Logger.log(url);
  return url;
}

function authCallback(request) {
  var ok = getService_().handleCallback(request);
  var ch = ok ? channel_() : null;
  var msg = ok ? ('Da ket noi kenh: ' + (ch ? ch.title + ' (' + ch.id + ')' : '?') + (ch && ch.id === GA_CHANNEL ? ' - DUNG KENH GOLDEN ARCH. Dong tab nay.' : ' - SAI KENH, hay chay lai va chon kenh Golden Arch.')) : 'Ket noi that bai.';
  PropertiesService.getScriptProperties().setProperty('authResult', new Date().toISOString() + ' ' + msg);
  return HtmlService.createHtmlOutput('<h2 style="font-family:sans-serif">' + msg + '</h2>');
}

function api_(method, url, opt) {
  opt = opt || {};
  opt.method = method;
  opt.headers = opt.headers || {};
  opt.headers.Authorization = 'Bearer ' + getService_().getAccessToken();
  opt.muteHttpExceptions = true;
  var r = UrlFetchApp.fetch(url, opt);
  if (r.getResponseCode() >= 300) throw new Error(r.getResponseCode() + ' ' + r.getContentText().slice(0, 300));
  return r;
}

function channel_() {
  var j = JSON.parse(api_('get', 'https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true').getContentText());
  return j.items && j.items.length ? { id: j.items[0].id, title: j.items[0].snippet.title } : null;
}

function upload_(v) {
  var blob = UrlFetchApp.fetch(BASE + v.file).getBlob();
  var meta = {
    snippet: { title: v.title, description: v.description || '', tags: v.tags || [], categoryId: v.categoryId || '26', defaultLanguage: 'vi', defaultAudioLanguage: 'vi' },
    status: { privacyStatus: v.privacy || 'public', selfDeclaredMadeForKids: false }
  };
  var init = api_('post', 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', {
    contentType: 'application/json; charset=UTF-8',
    headers: { 'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': String(blob.getBytes().length) },
    payload: JSON.stringify(meta)
  });
  var loc = init.getHeaders()['Location'] || init.getHeaders()['location'];
  var res = JSON.parse(api_('put', loc, { contentType: 'video/mp4', payload: blob.getBytes() }).getContentText());
  var info = { videoId: res.id, at: new Date().toISOString(), status: res.status && res.status.privacyStatus };
  if (v.thumbnail) {
    try {
      var tb = UrlFetchApp.fetch(BASE + v.thumbnail).getBlob();
      api_('post', 'https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId=' + res.id, { contentType: 'image/jpeg', payload: tb.getBytes() });
      info.thumb = 'ok';
    } catch (e) { info.thumb = String(e).slice(0, 200); }
  }
  return info;
}

function processQueue() {
  var props = PropertiesService.getScriptProperties();
  var svc = getService_();
  if (!svc.hasAccess()) { props.setProperty('lastRun', new Date().toISOString() + ' SKIP: chua ket noi kenh'); return; }
  var ch = channel_();
  if (!ch || ch.id !== GA_CHANNEL) { props.setProperty('lastRun', new Date().toISOString() + ' SKIP: sai kenh ' + (ch ? ch.id : 'none')); return; }
  var done = JSON.parse(props.getProperty('done') || '{}');
  var q = JSON.parse(UrlFetchApp.fetch(BASE + 'queue.json?t=' + Date.now()).getContentText());
  var log = [];
  q.videos.forEach(function (v) {
    if (done[v.id] || v.already_uploaded) return;
    if (v.publish_after && new Date(v.publish_after) > new Date()) return;
    try {
      done[v.id] = upload_(v);
      log.push(v.id + ' -> ' + done[v.id].videoId + ' (' + done[v.id].status + ')');
    } catch (e) {
      log.push(v.id + ' ERROR ' + e);
      props.setProperty('lastError', new Date().toISOString() + ' ' + v.id + ' ' + e);
    }
  });
  props.setProperty('done', JSON.stringify(done));
  props.setProperty('lastRun', new Date().toISOString() + ' ' + (log.join(' | ') || 'no new'));
  Logger.log(log.join('\n') || 'no new');
}

/** Tao lich chay moi gio */
function setup() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('processQueue').timeBased().everyHours(1).create();
  Logger.log('Trigger OK');
}

/** Xem trang thai */
function status() {
  var p = PropertiesService.getScriptProperties().getProperties();
  var out = { lastRun: p.lastRun, lastError: p.lastError, authResult: p.authResult, done: p.done, hasAccess: getService_().hasAccess() };
  Logger.log(JSON.stringify(out, null, 1));
  return out;
}
