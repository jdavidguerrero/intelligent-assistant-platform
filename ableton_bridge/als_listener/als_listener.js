/**
 * als_listener.js — ALS Listener WebSocket server
 *
 * Runs inside Max for Live via the `node.script` object.
 * Provides a WebSocket server on localhost:11005.
 *
 * Architecture
 * ────────────
 *   Max patch wiring:
 *
 *     [js lom_scanner.js]          (outlet 0 → inlet 0 of this script)
 *           ↑                      sends 'session_data <json>'
 *     [loadbang] → [node.script als_listener.js]
 *                         │
 *                         │  outlet 0 → [js lom_scanner.js] inlet
 *                         │  sends 'scan', 'set_parameter <json>', 'set_property <json>'
 *                         │
 *                    WebSocket port 11005
 *                         │
 *               ┌─────────┴──────────┐
 *           Client A            Client B
 *         (Python bridge)    (debug client)
 *
 * WebSocket protocol (JSON messages)
 * ────────────────────────────────────
 *   Server → Client:
 *     {"type":"session_state","data":{...}}    — full session on connect or 'get_session'
 *     {"type":"parameter_delta","data":{...}}  — real-time parameter change
 *     {"type":"pong","ts":1234567890}           — heartbeat reply
 *     {"type":"ack","id":"<cmd_id>","lom_path":"...","value":0.5}
 *     {"type":"error","id":"<cmd_id>","message":"..."}
 *
 *   Client → Server:
 *     {"type":"get_session"}                   — request full session snapshot
 *     {"type":"set_parameter","id":"<id>","lom_path":"...","value":0.5}
 *     {"type":"set_property","id":"<id>","lom_path":"...","property":"mute","value":1}
 *     {"type":"ping"}                          — heartbeat probe
 *
 * Reconnection
 * ────────────
 *   The Python bridge uses stateless-per-call connections (connect → op → close).
 *   The server handles this naturally — each connection receives a full
 *   session_state message immediately on connect.
 *
 * Dependencies (npm)
 * ──────────────────
 *   ws ^8.x  (install: cd ableton_bridge/als_listener && npm install)
 */

'use strict';

const Max = require('max-api');

// ── State ──────────────────────────────────────────────────────────────────

let wss = null;               // WebSocket.Server
let sessionCache = null;       // Last scanned session JSON string
let isInitialized = false;

// ── Initialization ────────────────────────────────────────────────────────

Max.addHandler('bang', () => startServer());
Max.addHandler('start', () => startServer());

async function startServer() {
    if (isInitialized) {
        Max.post('ALS Listener: already running on port 11005');
        return;
    }

    let WebSocket;
    try {
        WebSocket = require('ws');
    } catch (e) {
        Max.post('ALS Listener: ERROR — ws package not found. Run: npm install in als_listener/');
        Max.outlet('error', 'ws_not_installed');
        return;
    }

    wss = new WebSocket.Server({ port: 11005 });

    wss.on('listening', () => {
        Max.post('ALS Listener: WebSocket server ready on ws://localhost:11005');
        isInitialized = true;
        // Do NOT call Max.outlet('scan') here.
        // Max.outlet() delivers synchronously through the patch: the response
        // from lom_scanner arrives back at node.script inlet 0 before the
        // max-api IPC channel is fully ready, producing "not ready" errors.
        // The initial scan is triggered by [live.thisdevice] → [delay 1500]
        // in the patch, which fires ~1.5s after M4L init — well after the
        // node.script subprocess is ready to receive.
    });

    wss.on('error', (err) => {
        Max.post(`ALS Listener: server error — ${err.message}`);
        if (err.code === 'EADDRINUSE') {
            Max.post('ALS Listener: port 11005 is in use. Close other ALS Listener instances.');
        }
    });

    wss.on('connection', (ws, req) => {
        const clientAddr = req.socket.remoteAddress || 'unknown';
        Max.post(`ALS Listener: client connected from ${clientAddr}`);

        // Send cached session state immediately on connect
        if (sessionCache) {
            ws.send(JSON.stringify({ type: 'session_state', data: JSON.parse(sessionCache) }));
        } else {
            // Request fresh scan — will broadcast when ready
            Max.outlet('scan');
        }

        ws.on('message', (raw) => onClientMessage(ws, raw));
        ws.on('close', () => Max.post(`ALS Listener: client disconnected from ${clientAddr}`));
        ws.on('error', (err) => Max.post(`ALS Listener: client error — ${err.message}`));
    });

    // Heartbeat — detect stale connections every 30 s
    setInterval(() => {
        if (!wss) return;
        wss.clients.forEach((ws) => {
            if (ws.isAlive === false) { ws.terminate(); return; }
            ws.isAlive = false;
            ws.ping();
        });
    }, 30_000);
}

// ── Receive messages from lom_scanner (inlet 0) ───────────────────────────

/**
 * Full session state arrived from lom_scanner.js.
 * 'session_data <jsonString>'
 */
Max.addHandler('session_data', (jsonStr) => {
    sessionCache = jsonStr;
    broadcast({ type: 'session_state', data: JSON.parse(jsonStr) });
    Max.post(`ALS Listener: session scanned (${JSON.parse(jsonStr).tracks?.length || 0} tracks)`);
});

/**
 * On-demand device parameters arrived from lom_scanner.js.
 * 'device_params <jsonString>'
 */
Max.addHandler('device_params', (jsonStr) => {
    broadcast({ type: 'device_params', data: JSON.parse(jsonStr) });
});

/**
 * On-demand track clips arrived from lom_scanner.js.
 * 'track_clips <jsonString>'
 */
Max.addHandler('track_clips', (jsonStr) => {
    broadcast({ type: 'track_clips', data: JSON.parse(jsonStr) });
});

/**
 * Real-time parameter delta arrived from lom_scanner.js observer.
 * 'delta <jsonString>'
 */
Max.addHandler('delta', (jsonStr) => {
    broadcast({ type: 'parameter_delta', data: JSON.parse(jsonStr) });
});

/**
 * Ack from lom_scanner.js after a set_parameter / set_property command.
 * 'ack <jsonString>'
 */
Max.addHandler('ack', (jsonStr) => {
    broadcast({ type: 'ack', ...JSON.parse(jsonStr) });
});

/**
 * Error from lom_scanner.js.
 * 'error <jsonString>'
 */
Max.addHandler('error', (jsonStr) => {
    broadcast({ type: 'error', ...JSON.parse(jsonStr) });
});

// ── Handle messages from WebSocket clients ────────────────────────────────

function onClientMessage(ws, rawData) {
    let msg;
    try {
        msg = JSON.parse(rawData.toString());
    } catch (e) {
        ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }));
        return;
    }

    const id = msg.id || null;

    switch (msg.type) {
        case 'ping':
            ws.send(JSON.stringify({ type: 'pong', ts: Date.now() }));
            break;

        case 'get_session':
            if (sessionCache) {
                ws.send(JSON.stringify({ type: 'session_state', data: JSON.parse(sessionCache) }));
            } else {
                Max.outlet('scan');
            }
            break;

        case 'set_parameter':
            // Forward to lom_scanner.js — prefer lom_id (integer) over lom_path for reliable resolution
            Max.outlet('set_parameter', JSON.stringify({
                id,
                lom_id:   msg.lom_id   || null,
                lom_path: msg.lom_path || '',
                value: msg.value
            }));
            break;

        case 'set_property':
            Max.outlet('set_property', JSON.stringify({
                id,
                lom_id:   msg.lom_id   || null,
                lom_path: msg.lom_path || '',
                property: msg.property,
                value: msg.value
            }));
            break;

        case 'call_method':
            // Invoke an LOM method (e.g. start_playing, stop_playing)
            Max.outlet('call_method', JSON.stringify({
                id,
                lom_id:   msg.lom_id   || null,
                lom_path: msg.lom_path || '',
                method: msg.method,
                args: msg.args || []
            }));
            break;

        case 'get_device_params':
            // On-demand: request parameters for one device.
            // msg: { type, device_lom_id, track_idx, dev_idx }
            Max.outlet('scan_params_for_device', JSON.stringify({
                device_lom_id: msg.device_lom_id,
                track_idx:     msg.track_idx,
                dev_idx:       msg.dev_idx
            }));
            break;

        case 'get_track_clips':
            // On-demand: request clip list for one track.
            // msg: { type, track_lom_id, track_idx }
            Max.outlet('scan_clips_for_track', JSON.stringify({
                track_lom_id: msg.track_lom_id,
                track_idx:    msg.track_idx
            }));
            break;

        default:
            ws.send(JSON.stringify({ type: 'error', message: `Unknown message type: ${msg.type}` }));
    }
}

// ── Broadcast to all connected clients ───────────────────────────────────

function broadcast(payload) {
    if (!wss) return;
    const json = JSON.stringify(payload);
    wss.clients.forEach((client) => {
        if (client.readyState === 1 /* OPEN */) {
            client.send(json);
        }
    });
}

// ── Graceful shutdown ─────────────────────────────────────────────────────

Max.addHandler('stop', () => {
    if (wss) {
        wss.close(() => Max.post('ALS Listener: server stopped'));
        wss = null;
        isInitialized = false;
    }
});

Max.post('ALS Listener: script loaded — auto-starting WebSocket server...');

// Auto-start immediately on load. The external bang/start still works as
// a manual restart (guarded by isInitialized in startServer).
startServer();
