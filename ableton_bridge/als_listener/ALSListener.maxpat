{
	"patcher" : {
		"fileversion" : 1,
		"appversion" : {
			"major" : 9,
			"minor" : 0,
			"bugfix" : 10,
			"architecture" : "x64",
			"modernui" : 1
		},
		"classnamespace" : "dsp.midi",
		"rect" : [100.0, 100.0, 600.0, 340.0],
		"bglocked" : 0,
		"openinpresentation" : 0,
		"default_fontsize" : 12.0,
		"default_fontface" : 0,
		"default_fontname" : "Arial",
		"gridonopen" : 1,
		"gridsize" : [15.0, 15.0],
		"gridsnaponopen" : 1,
		"objectsnaponopen" : 1,
		"statusbarvisible" : 2,
		"toolbarvisible" : 1,
		"lefttoolbarpinned" : 0,
		"toptoolbarpinned" : 0,
		"righttoolbarpinned" : 0,
		"bottomtoolbarpinned" : 0,
		"toolbars_unpinned_last_save" : 0,
		"tallnewobj" : 0,
		"boxanimatetime" : 200,
		"enablehscroll" : 1,
		"enablevscroll" : 1,
		"devicewidth" : 0.0,
		"description" : "ALS Listener — Ableton Live Session WebSocket bridge on ws://localhost:11005",
		"digest" : "",
		"tags" : "",
		"style" : "",
		"subpatcher_template" : "",
		"assistshowspatchername" : 0,
		"boxes" : [
			{
				"box" : {
					"id" : "obj-title",
					"maxclass" : "comment",
					"text" : "ALS Listener  —  ws://localhost:11005",
					"patching_rect" : [15.0, 8.0, 320.0, 20.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial Bold",
					"fontsize" : 13.0,
					"textcolor" : [0.9, 0.5, 0.1, 1.0]
				}
			},
			{
				"box" : {
					"id" : "obj-btn",
					"maxclass" : "button",
					"patching_rect" : [15.0, 40.0, 24.0, 24.0],
					"numoutlets" : 1,
					"outlettype" : ["bang"],
					"numinlets" : 1,
					"style" : "",
					"parameter_enable" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-btn-label",
					"maxclass" : "comment",
					"text" : "click to restart server",
					"patching_rect" : [45.0, 45.0, 160.0, 18.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 10.0,
					"textcolor" : [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box" : {
					"id" : "obj-delay",
					"maxclass" : "newobj",
					"text" : "delay 3000",
					"patching_rect" : [15.0, 78.0, 90.0, 22.0],
					"numoutlets" : 1,
					"outlettype" : ["bang"],
					"numinlets" : 2,
					"fontname" : "Arial",
					"fontsize" : 12.0
				}
			},
			{
				"box" : {
					"id" : "obj-node",
					"maxclass" : "newobj",
					"text" : "node.script als_listener.js",
					"patching_rect" : [15.0, 115.0, 240.0, 22.0],
					"numoutlets" : 2,
					"outlettype" : ["", ""],
					"numinlets" : 2,
					"fontname" : "Arial",
					"fontsize" : 12.0
				}
			},
			{
				"box" : {
					"id" : "obj-print-status",
					"maxclass" : "newobj",
					"text" : "print als-node",
					"patching_rect" : [270.0, 115.0, 110.0, 22.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 12.0
				}
			},
			{
				"box" : {
					"id" : "obj-lom",
					"maxclass" : "newobj",
					"text" : "js lom_scanner.js",
					"patching_rect" : [15.0, 155.0, 160.0, 22.0],
					"numoutlets" : 2,
					"outlettype" : ["", ""],
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 12.0
				}
			},
			{
				"box" : {
					"id" : "obj-hint1",
					"maxclass" : "comment",
					"text" : "Auto-starts on load. Button restarts if port 11005 in use.",
					"patching_rect" : [15.0, 205.0, 500.0, 18.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 10.0,
					"textcolor" : [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box" : {
					"id" : "obj-hint2",
					"maxclass" : "comment",
					"text" : "Open Max console (cmd+M) to see connection status.",
					"patching_rect" : [15.0, 223.0, 420.0, 18.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 10.0,
					"textcolor" : [0.5, 0.5, 0.5, 1.0]
				}
			},
			{
				"box" : {
					"id" : "obj-hint3",
					"maxclass" : "comment",
					"text" : "Note: one 'not ready' warning at load is expected — device still works.",
					"patching_rect" : [15.0, 241.0, 500.0, 18.0],
					"numoutlets" : 0,
					"numinlets" : 1,
					"fontname" : "Arial",
					"fontsize" : 10.0,
					"textcolor" : [0.4, 0.4, 0.4, 1.0]
				}
			}
		],
		"lines" : [
			{
				"patchline" : {
					"source" : ["obj-btn", 0],
					"destination" : ["obj-delay", 0]
				}
			},
			{
				"patchline" : {
					"source" : ["obj-delay", 0],
					"destination" : ["obj-node", 0]
				}
			},
			{
				"patchline" : {
					"source" : ["obj-node", 0],
					"destination" : ["obj-lom", 0]
				}
			},
			{
				"patchline" : {
					"source" : ["obj-node", 1],
					"destination" : ["obj-print-status", 0]
				}
			},
			{
				"patchline" : {
					"source" : ["obj-lom", 1],
					"destination" : ["obj-node", 0]
				}
			}
		]
	}
}
