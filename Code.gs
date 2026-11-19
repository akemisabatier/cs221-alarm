/**
 * Adaptive Alarm – Google Sheets backend (Google Apps Script)
 *
 * Paste this into Extensions › Apps Script of the team's Google Sheet,
 * then Deploy › New deployment › Web app (Execute as: Me, Who has access: Anyone).
 * Copy the web app URL into API_URL at the top of index.html.
 *
 * One row per completed night, on a tab named "nights".
 */

var SHEET_NAME = 'nights';
var HEADERS = ['id', 'participant', 'bed_time', 'wake_time', 'hours_asleep', 'snoozes', 'rating',
               'bed_ms', 'wake_ms', 'tz_offset_min', 'saved_at'];

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) sh = ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) {
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
  }
  return sh;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function validParticipant_(p) {
  return typeof p === 'string' && /^[A-Z0-9_-]{1,20}$/.test(p);
}

function validId_(id) {
  return typeof id === 'string' && /^[A-Za-z0-9_-]{6,64}$/.test(id);
}

/** GET ?action=list&participant=P1  → that participant's nights */
function doGet(e) {
  try {
    var p = (e.parameter.participant || '').toUpperCase();
    if (e.parameter.action !== 'list' || !validParticipant_(p)) return json_({ ok: false, error: 'bad request' });
    var sh = getSheet_();
    var values = sh.getDataRange().getValues();
    var nights = [];
    for (var i = 1; i < values.length; i++) {
      var r = values[i];
      if (String(r[1]) !== p) continue;
      nights.push({ id: String(r[0]), bedAt: Number(r[7]), wakeAt: Number(r[8]), snoozes: Number(r[5]), rating: Number(r[6]) });
    }
    return json_({ ok: true, nights: nights });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/** POST body (text/plain JSON):
 *  {action:'upsert', participant, night:{id,bedAt,wakeAt,snoozes,rating}, tzOffset}
 *  {action:'delete', participant, id}
 */
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var body = JSON.parse(e.postData.contents);
    var p = String(body.participant || '').toUpperCase();
    if (!validParticipant_(p)) return json_({ ok: false, error: 'bad participant' });
    var sh = getSheet_();
    var values = sh.getDataRange().getValues();

    function findRow(id) {
      for (var i = 1; i < values.length; i++) {
        if (String(values[i][0]) === id && String(values[i][1]) === p) return i + 1; // 1-based sheet row
      }
      return -1;
    }

    if (body.action === 'delete') {
      if (!validId_(body.id)) return json_({ ok: false, error: 'bad id' });
      var rowD = findRow(body.id);
      if (rowD > 0) sh.deleteRow(rowD);
      return json_({ ok: true });
    }

    if (body.action === 'upsert') {
      var n = body.night || {};
      var bed = Number(n.bedAt), wake = Number(n.wakeAt), sn = Number(n.snoozes), rt = Number(n.rating);
      if (!validId_(n.id)) return json_({ ok: false, error: 'bad id' });
      if (!(bed > 1.6e12 && wake > bed && wake - bed < 20 * 3600000)) return json_({ ok: false, error: 'bad times' });
      if (!(sn >= 0 && sn <= 30 && Math.floor(sn) === sn)) return json_({ ok: false, error: 'bad snoozes' });
      if (!(rt >= 1 && rt <= 10 && Math.floor(rt) === rt)) return json_({ ok: false, error: 'bad rating' });
      var row = [n.id, p, new Date(bed), new Date(wake), Math.round((wake - bed) / 36000) / 100, sn, rt,
                 bed, wake, Number(body.tzOffset) || 0, new Date()];
      var rowU = findRow(n.id);
      if (rowU > 0) sh.getRange(rowU, 1, 1, row.length).setValues([row]);
      else sh.appendRow(row);
      return json_({ ok: true });
    }

    return json_({ ok: false, error: 'unknown action' });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
  }
}
