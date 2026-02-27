{
	"patcher": {
		"fileversion": 1,
		"appversion": {
			"major": 9,
			"minor": 0,
			"bugfix": 10,
			"architecture": "x64",
			"modernui": 1
		},
		"classnamespace": "dsp.midi",
		"rect": [100.0, 100.0, 680.0, 400.0],
		"bglocked": 0,
		"openinpresentation": 0,
		"default_fontsize": 12.0,
		"default_fontface": 0,
		"default_fontname": "Arial",
		"gridonopen": 1,
		"gridsize": [15.0, 15.0],
		"gridsnaponopen": 1,
		"objectsnaponopen": 1,
		"statusbarvisible": 2,
		"toolbarvisible": 1,
		"lefttoolbarpinned": 0,
		"toptoolbarpinned": 0,
		"righttoolbarpinned": 0,
		"bottomtoolbarpinned": 0,
		"toolbars_unpinned_last_save": 0,
		"tallnewobj": 0,
		"boxanimatetime": 200,
		"enablehscroll": 1,
		"enablevscroll": 1,
		"devicewidth": 0.0,
		"description": "ALS Listener \u2014 Ableton Live Session WebSocket bridge on ws://localhost:11005",
		"digest": "",
		"tags": "",
		"style": "",
		"subpatcher_template": "",
		"assistshowspatchername": 0,
		"boxes": [
			{
				"box": {
					"id": "obj-title",
					"maxclass": "comment",
					"text": "ALS Listener  \u2014  ws://localhost:11005",
					"patching_rect": [15.0, 8.0, 320.0, 20.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial Bold",
					"fontsize": 13.0,
					"textcolor": [0.9, 0.5, 0.1, 1.0]
				}
			},
			{
				"box": {
					"id": "obj-mfl",
					"maxclass": "newobj",
					"text": "live.thisdevice",
					"patching_rect": [370.0, 35.0, 115.0, 22.0],
					"numoutlets": 2,
					"outlettype": ["bang", "bang"],
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-mfl-delay",
					"maxclass": "newobj",
					"text": "delay 1500",
					"patching_rect": [370.0, 72.0, 90.0, 22.0],
					"numoutlets": 1,
					"outlettype": ["bang"],
					"numinlets": 2,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-mfl-label",
					"maxclass": "comment",
					"text": "M4L ready \u2192 triggers initial scan after 1.5s",
					"patching_rect": [475.0, 40.0, 210.0, 18.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 10.0,
					"textcolor": [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box": {
					"id": "obj-btn",
					"maxclass": "button",
					"patching_rect": [15.0, 35.0, 24.0, 24.0],
					"numoutlets": 1,
					"outlettype": ["bang"],
					"numinlets": 1,
					"style": "",
					"parameter_enable": 0
				}
			},
			{
				"box": {
					"id": "obj-btn-label",
					"maxclass": "comment",
					"text": "click to restart server",
					"patching_rect": [45.0, 40.0, 160.0, 18.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 10.0,
					"textcolor": [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box": {
					"id": "obj-delay",
					"maxclass": "newobj",
					"text": "delay 3000",
					"patching_rect": [15.0, 72.0, 90.0, 22.0],
					"numoutlets": 1,
					"outlettype": ["bang"],
					"numinlets": 2,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-node",
					"maxclass": "newobj",
					"text": "node.script als_listener.js",
					"patching_rect": [15.0, 115.0, 240.0, 22.0],
					"numoutlets": 2,
					"outlettype": ["", ""],
					"numinlets": 2,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-print-status",
					"maxclass": "newobj",
					"text": "print als-node",
					"patching_rect": [270.0, 115.0, 110.0, 22.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-lom",
					"maxclass": "newobj",
					"text": "js lom_scanner.js",
					"patching_rect": [15.0, 160.0, 160.0, 22.0],
					"numoutlets": 1,
					"outlettype": [""],
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-route-bang",
					"maxclass": "newobj",
					"text": "route bang",
					"patching_rect": [185.0, 160.0, 80.0, 22.0],
					"numoutlets": 2,
					"outlettype": ["", ""],
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 12.0
				}
			},
			{
				"box": {
					"id": "obj-lom-label",
					"maxclass": "comment",
					"text": "single outlet \u2192 route bang: out0 absorbs compile-time bangs, out1 passes session_data/delta/ack/error \u2192 node.script",
					"patching_rect": [15.0, 185.0, 640.0, 18.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 10.0,
					"textcolor": [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box": {
					"id": "obj-hint1",
					"maxclass": "comment",
					"text": "no auto-scan from als_listener.js \u2014 live.thisdevice is the only startup scan trigger (fires 1.5s after M4L init, node.script is always ready)",
					"patching_rect": [15.0, 210.0, 640.0, 18.0],
					"numoutlets": 0,
					"numinlets": 1,
					"fontname": "Arial",
					"fontsize": 10.0,
					"textcolor": [0.5, 0.5, 0.5, 1.0]
				}
			}
		],
		"lines": [
			{
				"patchline": {
					"source": ["obj-mfl", 0],
					"destination": ["obj-mfl-delay", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-mfl-delay", 0],
					"destination": ["obj-lom", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-btn", 0],
					"destination": ["obj-delay", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-delay", 0],
					"destination": ["obj-node", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-node", 0],
					"destination": ["obj-lom", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-node", 1],
					"destination": ["obj-print-status", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-lom", 0],
					"destination": ["obj-route-bang", 0]
				}
			},
			{
				"patchline": {
					"source": ["obj-route-bang", 1],
					"destination": ["obj-node", 0]
				}
			}
		]
	}
}
