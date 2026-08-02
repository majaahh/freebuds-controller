/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cli.h"
#include "controller.h"
#include "frame.h"
#include "protocol.h"

#define MAC_FILE ".mac"

static const char *const LP_NAMES[18] = {
    "Voice assistant",
    "Play/Pause",
    "Next track",
    "NC on/off",
    "Play/Next",
    "NC on/off/ambient",
    "NC on/ambient",
    "Previous track",
    "Play/Previous",
    "NC off/ambient",
    "Noise control",
    "Reject call",
    NULL,
    NULL,
    "Song recognition",
    "Freestyle listen",
    NULL,
    "Health query",
};

static const char *const DC_NAMES[10] = {
    "Voice assistant", "Play/Pause",        "Next track",    "NC on/off",
    "Play/Next",       "NC on/off/ambient", "NC on/ambient", "Previous track",
    "Play/Previous",   "NC off/ambient",
};

static const char *const TRIPLE_NAMES[8] = {
    "Voice assistant", "Play/Pause", "Next track", "NC on/off",
    "Noise control",   NULL,         NULL,         "Previous track",
};

static const char *const SLIDE_NAMES[2] = {"Volume", "Prev/Next track"};

static const char *const PINCH_NAMES[6] = {
    "Face-to-face translate", "Voice memo", "Pairing",
    "Freestyle listen",       "Pinch chat", "Song recognition",
};

static const char *action_name(int g, int action, char *buf, size_t sz) {
  const char *n = NULL;
  if (action == 255)
    n = "None";
  else if (g == 0 || g == 5)
    n = (action >= 0 && action < 18) ? LP_NAMES[action] : NULL;
  else if (g == 1)
    n = (action >= 0 && action < 6) ? PINCH_NAMES[action] : NULL;
  else if (g == 2)
    n = (action >= 0 && action < 2) ? SLIDE_NAMES[action] : NULL;
  else if (g == 3)
    n = (action >= 0 && action < 10) ? DC_NAMES[action] : NULL;
  else if (g == 4)
    n = (action >= 0 && action < 8) ? TRIPLE_NAMES[action] : NULL;
  if (n) {
    snprintf(buf, sz, "%s", n);
    return buf;
  }
  snprintf(buf, sz, "Unknown (%d)", action);
  return buf;
}

static const char *nc_mode_name(int mode) {
  if (mode >= 0 && mode < 3)
    return FB_NC_MODES[mode];
  return "Unknown";
}

static const char *nc_level_name(int level) {
  if (level >= 0 && level < 4)
    return FB_NC_LEVELS[level];
  return "Unknown";
}

static const char *eq_mode_name(int mode) {
  switch (mode) {
  case 1:
    return FB_EQ_MODES[0];
  case 2:
    return FB_EQ_MODES[1];
  case 3:
    return FB_EQ_MODES[2];
  case 9:
    return FB_EQ_MODES[3];
  default:
    return "Unknown";
  }
}

void fb_scan_freebuds(fb_scan_results *out, int scan_time) {
  char cmd[256];
  FILE *p;

  memset(out, 0, sizeof(*out));

  snprintf(cmd, sizeof(cmd), "bluetoothctl --timeout %d scan on 2>/dev/null",
           scan_time);
  p = popen(cmd, "r");
  if (p) {
    while (fgets(cmd, sizeof(cmd), p)) {
    }
    pclose(p);
  }

  p = popen("bluetoothctl devices 2>/dev/null", "r");
  if (!p)
    return;
  while (fgets(cmd, sizeof(cmd), p)) {
    char addr[64] = "", name[128] = "";
    fb_scan_entry *e;
    if (sscanf(cmd, "Device %63s %127[^\n]", addr, name) == 2) {
      if (strstr(name, "FreeBuds") || strstr(name, "freebuds") ||
          strcmp(name, "Orange") == 0) {
        out->items =
            realloc(out->items, (out->count + 1) * sizeof(fb_scan_entry));
        e = &out->items[out->count];
        memset(e, 0, sizeof(*e));
        snprintf(e->name, sizeof(e->name), "%s", name);
        snprintf(e->address, sizeof(e->address), "%s", addr);
        out->count++;
      }
    }
  }
  pclose(p);
}

int fb_is_paired(const char *address) {
  char cmd[256];
  FILE *p;
  int paired = 0;

  snprintf(cmd, sizeof(cmd), "bluetoothctl info %s 2>/dev/null", address);
  p = popen(cmd, "r");
  if (!p)
    return 0;
  while (fgets(cmd, sizeof(cmd), p)) {
    if (strstr(cmd, "Paired: yes")) {
      paired = 1;
      break;
    }
  }
  pclose(p);
  return paired;
}

int fb_save_mac(const char *mac, const char *path) {
  FILE *f = fopen(path, "w");
  if (!f)
    return 0;
  fprintf(f, "%s\n", mac);
  fclose(f);
  return 1;
}

const char *fb_load_mac(const char *path, char *out, size_t outsz) {
  FILE *f = fopen(path, "r");
  if (!f)
    return NULL;
  if (fgets(out, (int)outsz, f)) {
    size_t n = strlen(out);
    while (n > 0 &&
           (out[n - 1] == '\n' || out[n - 1] == '\r' || out[n - 1] == ' '))
      out[--n] = '\0';
    fclose(f);
    if (fb_valid_mac(out))
      return out;
    return NULL;
  }
  fclose(f);
  return NULL;
}

static void print_status(const char *label, uint32_t status) {
  if (status == FB_STATUS_NOT_SUPPORTED)
    printf("%s: Not supported by device\n", label);
  else
    printf("%s: status=0x%08X\n", label, status);
}

void print_run_help(void) {
  printf("Available commands:\n");
  printf("  bat                            - Get battery levels\n");
  printf("  ver                            - Get firmware/device version\n");
  printf("  info                           - Fetch all settings at once\n");
  printf("  gesture <type> [<side> <act>]  - Get/set gesture "
         "(lp|pinch|slide|dc|triple|lhold|nc)\n");
  printf("  anc [<mode>|level <name|0-3>]  - Get/set noise control "
         "(off|on|aware; level: general|cozy|ultra|dynamic)\n");
  printf("  sfx [<name>]                   - Get/set sound effect "
         "(default|bass|treble|voices)\n");
  printf("  lang [<code>]                  - Get/set language\n");
  printf("  misc [<name> [on|off]]         - Get/set misc features\n");
  printf("  devices [<action> [<mac|idx>]] - List/connect/disconnect/unpair "
         "devices stored on the buds\n");
  printf("  raw <hex>                      - Send raw command bytes\n");
}

static void print_devices_help(void) {
  printf("Paired device management (list stored on the buds):\n");
  printf("  devices                       - List all devices\n");
  printf("  devices connect <mac|idx>     - Connect the buds to a device\n");
  printf("  devices disconnect <mac|idx>  - Disconnect from a device\n");
  printf("  devices unpair <mac|idx>      - Forget a device on the buds\n");
  printf("  devices primary <mac|idx>     - Set the default/primary device\n");
}

static void print_misc_help(void) {
  printf("Misc settings:\n");
  printf("  misc <name> [on|off] - Get/set\n");
  printf("\n");
  printf("  Settable:\n");
  printf("    greet   - Voice prompts\n");
  printf("    wear    - Wear detection\n");
  printf("    ivol    - Intellect volume\n");
  printf("    save    - Saving mode\n");
  printf("    glat    - Game low latency\n");
  printf("    dual    - Dual connect\n");
  printf("    trans   - Translate mode\n");
  printf("    venh    - Voice enhance\n");
  printf("    32k     - 32K HD voice\n");
  printf("    hd      - HD sound switch\n");
  printf("    lre     - L/R ear recognition\n");
  printf("    wind    - Wind mode\n");
  printf("    silent  - Silent upgrade\n");
  printf("    health  - Health alerts\n");
  printf("\n");
  printf("  Read-only:\n");
  printf("    wearst  - Wearing status\n");
  printf("    dormant - Dormant time (misc dormant <seconds> sets)\n");
  printf("    pair    - Pair state (misc pair on enters pairing)\n");
  printf("    fit     - Earplug fit check (misc fit exit exits)\n");
  printf("    fitver  - Fit-detect version\n");
  printf("    hb      - Heartbeat\n");
  printf("    btmain  - BT main status\n");
  printf("    cover   - Close-cover remind\n");
  printf("    music   - Music mode\n");
  printf("    ambient - Ambient sound\n");
  printf("    conn    - Connect ability\n");
}

static void print_gesture_help(void) {
  printf("Gesture commands:\n");
  printf("  gesture <gesture>              - Get gesture action\n");
  printf("  gesture <gesture> <side> <act> - Set gesture action\n");
  printf("  gesture nc                     - Show noise control assignments\n");
  printf(
      "  gesture nc <gesture> <side>    - Assign noise control to a gesture\n");
  printf("\n");
  printf("  Side: 1=left, 2=right\n");
  printf(
      "  Gestures: lp (long press), pinch/sp, slide/sl, dc (double click),\n");
  printf("            triple/tri, lhold (light hold)\n");
  printf("\n");
  printf("  Common actions: 0=Voice assistant 1=Play/Pause 2=Next 3=NC on/off "
         "7=Previous 255=None\n");
  printf("  Long press extras: 10=Noise control 11=Reject call 14=Song "
         "recognition 15=Freestyle listen 17=Health query\n");
  printf("  Double click extras: 4=Play/Next 5=NC on/off/ambient 6=NC "
         "on/ambient 8=Play/Previous 9=NC off/ambient\n");
  printf("  Pinch actions: 0=Translate 1=Voice memo 2=Pairing 3=Freestyle "
         "4=Pinch chat 5=Song recognition\n");
  printf("  Slide actions: 0=Volume 1=Prev/Next track\n");
  printf("  Triple click: 0=Assistant 1=Play/Pause 2=Next 3=NC on/off 4=Noise "
         "control\n");
}

static const char *resolve_address(const char *address, char *out,
                                   size_t outsz) {
  char loaded[32];
  fb_scan_results scan;

  if (address) {
    snprintf(out, outsz, "%s", address);
    return out;
  }

  if (fb_load_mac(MAC_FILE, loaded, sizeof(loaded))) {
    snprintf(out, outsz, "%s", loaded);
    return out;
  }

  printf("Scanning for FreeBuds...\n");
  fb_scan_freebuds(&scan, 8);
  if (scan.count > 0) {
    snprintf(out, outsz, "%s", scan.items[0].address);
    printf("Found: %s\n", out);
    fb_save_mac(out, MAC_FILE);
    free(scan.items);
    return out;
  }
  free(scan.items);
  printf("No FreeBuds found. Use --address or create a .mac file.\n");
  return NULL;
}

int fb_cmd_scan(int time_sec, const char *save_path) {
  fb_scan_results scan;
  size_t i;
  FILE *f = NULL;

  printf("\nScanner\n\n");
  fb_scan_freebuds(&scan, time_sec);
  if (scan.count == 0) {
    printf("No FreeBuds found. Ensure they're in pairing mode.\n\n");
    return 0;
  }

  printf("Found %zu:\n\n", scan.count);
  for (i = 0; i < scan.count; i++) {
    printf("  [%zu] %s\n", i, scan.items[i].name);
    printf("      Address: %s\n", scan.items[i].address);
    printf("      Paired:  %s\n",
           fb_is_paired(scan.items[i].address) ? "yes" : "no");
    if (scan.items[i].has_rssi)
      printf("      RSSI: %d\n", scan.items[i].rssi);
    printf("\n");
  }

  if (save_path) {
    f = fopen(save_path, "w");
    if (f) {
      fprintf(f, "[\n");
      for (i = 0; i < scan.count; i++) {
        fprintf(f,
                "  {\"name\": \"%s\", \"address\": \"%s\", \"rssi\": %d}%s\n",
                scan.items[i].name, scan.items[i].address,
                scan.items[i].has_rssi ? scan.items[i].rssi : 0,
                i + 1 < scan.count ? "," : "");
      }
      fprintf(f, "]\n");
      fclose(f);
    }
  }

  free(scan.items);
  return 1;
}

static const fb_feature *feature_by_key(const char *key) {
  size_t i;
  for (i = 0; i < FB_FEATURABLE_COUNT; i++) {
    if (strcmp(FB_FEATURABLE[i].key, key) == 0)
      return &FB_FEATURABLE[i];
  }
  return NULL;
}

static uint8_t *feature_set_payload(const char *key, int enable, size_t *len) {
  if (strcmp(key, "greet") == 0)
    return fb_cmd_set_greet(enable, len);
  if (strcmp(key, "wear") == 0)
    return fb_cmd_set_wear(enable, len);
  if (strcmp(key, "ivol") == 0)
    return fb_cmd_set_intellect_volume(enable, len);
  if (strcmp(key, "save") == 0)
    return fb_cmd_set_saving_mode(enable, len);
  if (strcmp(key, "glat") == 0)
    return fb_cmd_set_game_low_latency(enable, len);
  if (strcmp(key, "dual") == 0)
    return fb_cmd_set_dual_connect(enable, len);
  if (strcmp(key, "trans") == 0)
    return fb_cmd_set_translate_mode(enable, len);
  if (strcmp(key, "venh") == 0)
    return fb_cmd_set_voice_enhance(enable, len);
  if (strcmp(key, "32k") == 0)
    return fb_cmd_set_32k_hd(enable, len);
  if (strcmp(key, "hd") == 0)
    return fb_cmd_set_hd_switch(enable, len);
  if (strcmp(key, "lre") == 0)
    return fb_cmd_set_left_right_ear(enable, len);
  if (strcmp(key, "wind") == 0)
    return fb_cmd_set_wind_mode(enable, len);
  if (strcmp(key, "silent") == 0)
    return fb_cmd_set_silent_upgrade(enable, len);
  if (strcmp(key, "health") == 0)
    return fb_cmd_set_health_alerts(enable, len);
  return NULL;
}

static int is_on_value(const char *s) {
  return strcmp(s, "on") == 0 || strcmp(s, "1") == 0 ||
         strcmp(s, "true") == 0 || strcmp(s, "yes") == 0;
}

static int is_off_value(const char *s) {
  return strcmp(s, "off") == 0 || strcmp(s, "0") == 0 ||
         strcmp(s, "false") == 0 || strcmp(s, "no") == 0;
}

static int run_misc_get(fb_ctrl *ctrl, const char *fname) {
  const fb_feature *feat = feature_by_key(fname);
  fb_boolres br;
  fb_uintres ur;
  fb_wearres wr;
  char label[64];
  int got;

  if (feat) {
    got = fb_ctrl_get_bool(ctrl, &br, feat->get, feat->get_len, feat->svc,
                           feat->cmd, feat->set_cmd);
    if (got) {
      if (br.has_enabled)
        printf("%s: %s\n", feat->name, br.enabled ? "On" : "Off");
      else if (br.has_status)
        print_status(feat->name, br.status);
      else
        printf("%s: raw=%s\n", feat->name, br.raw_hex);
    } else
      printf("no response\n");
    return 0;
  }

  if (strcmp(fname, "wearst") == 0) {
    got = fb_ctrl_get_wearing_status(ctrl, &wr);
    if (got) {
      if (wr.has_status)
        print_status("Wearing status", wr.status);
      else {
        char left[16], right[16];
        snprintf(left, sizeof(left), "%s",
                 wr.has_left_ear ? (wr.left_in ? "In" : "Out") : "?");
        snprintf(right, sizeof(right), "%s",
                 wr.has_right_ear ? (wr.right_in ? "In" : "Out") : "?");
        printf("Wearing status: L=%s R=%s\n", left, right);
      }
    } else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "dormant") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_GET_DORMANT_TIME,
                           sizeof(FB_CMD_GET_DORMANT_TIME), 0x2B, 0x48);
    if (got && ur.has_value)
      printf("Dormant time: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Dormant time", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "pair") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_QUERY_PAIR,
                           sizeof(FB_CMD_QUERY_PAIR), 0x2B, 0x8F);
    if (got && ur.has_value)
      printf("Pair state: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Pair state", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "fit") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_GET_FIT_CHECK,
                           sizeof(FB_CMD_GET_FIT_CHECK), 0x2B, 0x26);
    if (got && ur.has_value)
      printf("Earplug fit check: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Earplug fit check", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "fitver") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_GET_FIT_DETECT_VERSION,
                           sizeof(FB_CMD_GET_FIT_DETECT_VERSION), 0x2B, 0x37);
    if (got && ur.has_value)
      printf("Fit-detect version: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Fit-detect version", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "hb") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_HEARTBEAT,
                           sizeof(FB_CMD_HEARTBEAT), 0x2B, 0x4E);
    if (got && ur.has_value)
      printf("Heartbeat: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Heartbeat", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "btmain") == 0) {
    got = fb_ctrl_get_bool(ctrl, &br, FB_CMD_GET_BT_MAIN_STATUS,
                           sizeof(FB_CMD_GET_BT_MAIN_STATUS), 0x2B, 0x6A, 0x6A);
    if (got && br.has_enabled)
      printf("BT main status: %s\n", br.enabled ? "On" : "Off");
    else if (got && br.has_status)
      print_status("BT main status", br.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "cover") == 0) {
    got = fb_ctrl_get_bool(ctrl, &br, FB_CMD_GET_CLOSE_COVER_REMIND,
                           sizeof(FB_CMD_GET_CLOSE_COVER_REMIND), 0x2B, 0x7F,
                           0x7F);
    if (got && br.has_enabled)
      printf("Close-cover remind: %s\n", br.enabled ? "On" : "Off");
    else if (got && br.has_status)
      print_status("Close-cover remind", br.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "music") == 0) {
    got = fb_ctrl_get_uint(ctrl, &ur, FB_CMD_GET_MUSIC_MODE,
                           sizeof(FB_CMD_GET_MUSIC_MODE), 0x2B, 0x53);
    if (got && ur.has_value)
      printf("Music mode: %u\n", ur.value);
    else if (got && ur.has_status)
      print_status("Music mode", ur.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "ambient") == 0) {
    got = fb_ctrl_get_bool(ctrl, &br, FB_CMD_GET_AMBIENT_SOUND,
                           sizeof(FB_CMD_GET_AMBIENT_SOUND), 0x2B, 0x2C, 0x2C);
    if (got && br.has_enabled)
      printf("Ambient sound: %s\n", br.enabled ? "On" : "Off");
    else if (got && br.has_status)
      print_status("Ambient sound", br.status);
    else
      printf("no response\n");
    return 0;
  }
  if (strcmp(fname, "conn") == 0) {
    got =
        fb_ctrl_get_bool(ctrl, &br, FB_CMD_GET_CONNECT_ABILITY,
                         sizeof(FB_CMD_GET_CONNECT_ABILITY), 0x2B, 0x2D, 0x2D);
    if (got && br.has_enabled)
      printf("Connect ability: %s\n", br.enabled ? "On" : "Off");
    else if (got && br.has_status)
      print_status("Connect ability", br.status);
    else
      printf("no response\n");
    return 0;
  }

  snprintf(label, sizeof(label), "Unknown feature '%s'. Use: misc help", fname);
  printf("%s\n", label);
  return 0;
}

static int run_misc(fb_ctrl *ctrl, int argc, char **argv) {
  const char *fname;
  fb_setres sr;
  uint8_t *payload;
  size_t payload_len;
  int got;

  if (argc < 1) {
    print_misc_help();
    return 0;
  }
  fname = argv[0];

  if (strcmp(fname, "help") == 0 || strcmp(fname, "-h") == 0) {
    print_misc_help();
    return 0;
  }

  if (strcmp(fname, "dormant") == 0 && argc >= 2) {
    got = fb_ctrl_set_dormant_time(ctrl, &sr, 0, atoi(argv[1]));
    if (got && sr.has_success && sr.success)
      printf("Dormant time: set to %s s\n", argv[1]);
    else if (got)
      printf("Dormant time: set failed\n");
    else
      printf("no response\n");
    return 0;
  }

  if (strcmp(fname, "pair") == 0 && argc >= 2 && is_on_value(argv[1])) {
    got = fb_ctrl_start_pair(ctrl, &sr);
    if (got && sr.has_success && sr.success)
      printf("Pairing mode: enabled\n");
    else if (got)
      printf("Pairing mode: set failed\n");
    else
      printf("no response\n");
    return 0;
  }

  if (strcmp(fname, "fit") == 0 && argc >= 2 && strcmp(argv[1], "exit") == 0) {
    got = fb_ctrl_exit_fit_check(ctrl, &sr);
    if (got && sr.has_success && sr.success)
      printf("Fit check: exited\n");
    else if (got)
      printf("Fit check: exit failed\n");
    else
      printf("no response\n");
    return 0;
  }

  if (argc >= 2 && (is_on_value(argv[1]) || is_off_value(argv[1]))) {
    int enable = is_on_value(argv[1]);
    const fb_feature *feat = feature_by_key(fname);
    if (!feat) {
      printf("Unknown feature '%s'. Use: misc help\n", fname);
      return 0;
    }
    payload = feature_set_payload(fname, enable, &payload_len);
    if (!payload) {
      printf("'%s' is read-only\n", feat->name);
      return 0;
    }
    got = fb_ctrl_set_bool(ctrl, &sr, payload, payload_len, feat->svc,
                           feat->set_cmd);
    free(payload);
    if (got && sr.has_success && sr.success)
      printf("%s: %s\n", feat->name, enable ? "On" : "Off");
    else if (got && sr.has_status)
      printf("%s: set failed (status=0x%08X)\n", feat->name, sr.status);
    else if (got)
      printf("%s: set failed\n", feat->name);
    else
      printf("no response\n");
    return 0;
  }

  return run_misc_get(ctrl, fname);
}

static int run_gesture_get(fb_ctrl *ctrl, int g) {
  fb_touchres tr;
  char buf[64];
  size_t i;

  if (!fb_ctrl_get_touch(ctrl, &tr, &FB_GESTURES[g])) {
    printf("no response\n");
    return 0;
  }
  if (tr.has_status) {
    print_status(FB_GESTURES[g].name, tr.status);
    return 0;
  }
  if (tr.has_left || tr.has_right) {
    if (tr.has_left)
      printf("%s: Left=%s", FB_GESTURES[g].name,
             action_name(g, tr.left, buf, sizeof(buf)));
    else
      printf("%s: Left=unset", FB_GESTURES[g].name);
    if (tr.has_right)
      printf(", Right=%s\n", action_name(g, tr.right, buf, sizeof(buf)));
    else
      printf(", Right=unset\n");
    return 0;
  }
  if (tr.supported_count > 0) {
    printf("%s: supported:", FB_GESTURES[g].name);
    for (i = 0; i < tr.supported_count; i++)
      printf(" %s", action_name(g, tr.supported[i], buf, sizeof(buf)));
    printf("\n");
    return 0;
  }
  printf("%s: raw=%s\n", FB_GESTURES[g].name, tr.raw_hex);
  return 0;
}

static int run_gesture_set(fb_ctrl *ctrl, int g, int side, int action) {
  fb_setres sr;
  char buf[64];

  if (!fb_ctrl_set_touch(ctrl, &sr, &FB_GESTURES[g], side, action)) {
    printf("no response\n");
    return 0;
  }
  if (sr.has_success && sr.success) {
    printf("%s: %s -> %s\n", FB_GESTURES[g].name,
           side == FB_SIDE_LEFT ? "Left" : "Right",
           action_name(g, action, buf, sizeof(buf)));
  } else if (sr.has_status) {
    printf("%s: set failed (status=0x%08X)\n", FB_GESTURES[g].name, sr.status);
  } else {
    printf("%s: set failed\n", FB_GESTURES[g].name);
  }
  return 0;
}

static int run_nc(fb_ctrl *ctrl, int argc, char **argv) {
  size_t i;
  int g;
  int side;

  if (argc == 0) {
    int assigned = 0;
    for (i = 0; i < FB_GESTURE_COUNT; i++) {
      fb_touchres tr;
      int nc = FB_GESTURES[i].nc_action;
      if (nc < 0)
        continue;
      if (!fb_ctrl_get_touch(ctrl, &tr, &FB_GESTURES[i]))
        continue;
      if (tr.has_left && tr.left == nc) {
        printf("  %s (Left)\n", FB_GESTURES[i].name);
        assigned = 1;
      }
      if (tr.has_right && tr.right == nc) {
        printf("  %s (Right)\n", FB_GESTURES[i].name);
        assigned = 1;
      }
    }
    if (!assigned)
      printf("No gesture set to noise control. Use: gesture nc <gesture> "
             "<side>\n");
    return 0;
  }

  if (argc != 2) {
    printf("Usage: gesture nc <gesture> <side>\n");
    return 0;
  }

  g = fb_gesture_from_alias(argv[0]);
  if (g < 0) {
    printf("Unknown gesture. Use: lp, pinch, slide, dc, triple, lhold\n");
    return 0;
  }
  if (FB_GESTURES[g].nc_action < 0) {
    printf("%s has no noise-control action\n", FB_GESTURES[g].name);
    return 0;
  }
  side = atoi(argv[1]);
  if (side != FB_SIDE_LEFT && side != FB_SIDE_RIGHT) {
    printf("Side must be 1 (left) or 2 (right)\n");
    return 0;
  }

  {
    fb_setres sr;
    if (!fb_ctrl_set_touch(ctrl, &sr, &FB_GESTURES[g], side,
                           FB_GESTURES[g].nc_action)) {
      printf("No response\n");
      return 0;
    }
    if (sr.has_success && sr.success)
      printf("%s (%s) -> Noise control\n", FB_GESTURES[g].name,
             side == FB_SIDE_LEFT ? "Left" : "Right");
    else if (sr.has_status)
      printf("Set failed (status=0x%08X)\n", sr.status);
    else
      printf("Set failed\n");
  }
  return 0;
}

static int run_gesture(fb_ctrl *ctrl, int argc, char **argv) {
  int g, side, action;

  if (argc == 0 || strcmp(argv[0], "help") == 0 || strcmp(argv[0], "-h") == 0) {
    print_gesture_help();
    return 0;
  }

  if (strcmp(argv[0], "nc") == 0)
    return run_nc(ctrl, argc - 1, argv + 1);

  g = fb_gesture_from_alias(argv[0]);
  if (g < 0) {
    printf(
        "Unknown gesture '%s'. Use: lp, pinch, slide, dc, triple, lhold, nc\n",
        argv[0]);
    return 0;
  }

  if (argc == 1)
    return run_gesture_get(ctrl, g);

  if (argc == 3) {
    side = atoi(argv[1]);
    action = atoi(argv[2]);
    if (side != FB_SIDE_LEFT && side != FB_SIDE_RIGHT) {
      printf("Side must be 1 (left) or 2 (right)\n");
      return 0;
    }
    return run_gesture_set(ctrl, g, side, action);
  }

  printf("Usage: gesture %s [<side(1|2)> <action>]\n", argv[0]);
  return 0;
}

static int run_get_noise_mode(fb_ctrl *ctrl) {
  fb_ancres a1, a2, a3;

  if (fb_ctrl_get_anc_state(ctrl, &a1) && a1.has_mode) {
    printf("Noise control: %s\n", nc_mode_name(a1.mode));
    return 0;
  }
  if (fb_ctrl_query_nr_mode(ctrl, &a2) && a2.has_mode) {
    printf("Noise control: %s\n", nc_mode_name(a2.mode));
    return 0;
  }
  if (fb_ctrl_get_anc_mode_level(ctrl, &a3) && a3.has_mode) {
    printf("Noise control: %s\n", nc_mode_name(a3.mode));
    return 0;
  }
  printf("No response. Device may not support direct ANC mode control; try "
         "'gesture nc' to assign noise control to a gesture.\n");
  return 0;
}

static int run_anc(fb_ctrl *ctrl, int argc, char **argv) {
  fb_setres sr;
  int mode, level;

  if (argc >= 1 && strcmp(argv[0], "level") == 0) {
    if (argc < 2) {
      printf("Usage: anc level <general|cozy|ultra|dynamic> (or 0-3)\n");
      return 0;
    }
    if (!fb_resolve_anc_level(argv[1], &level)) {
      printf("Unknown ANC level. Use: general|cozy|ultra|dynamic (or 0-3)\n");
      return 0;
    }
    if (fb_ctrl_set_anc_level(ctrl, &sr, level)) {
      if (sr.has_success && sr.success)
        printf("ANC level: set to %s\n", nc_level_name(level));
      else
        printf("ANC level: set failed\n");
    } else
      printf("no response\n");
    return 0;
  }

  if (argc >= 1) {
    if (!fb_alias_value(FB_NC_MODE_ALIASES, argv[0], &mode)) {
      printf("Unknown mode '%s'. Use: off|on|aware (or 0|1|2)\n", argv[0]);
      return 0;
    }
    if (fb_ctrl_set_noise_mode(ctrl, &sr, mode)) {
      if (sr.has_success && sr.success)
        printf("Noise control: %s\n", nc_mode_name(mode));
      else
        printf("Noise control: set failed\n");
    } else
      printf("no response\n");
    return 0;
  }

  return run_get_noise_mode(ctrl);
}

static int run_sfx(fb_ctrl *ctrl, int argc, char **argv) {
  fb_eqres eq;
  fb_setres sr;
  int mode;
  size_t i;

  if (argc >= 1) {
    if (!fb_resolve_eq_mode(argv[0], &mode)) {
      printf("Unknown sound effect '%s'. Use: default|bass|treble|voices (or "
             "1|2|3|9)\n",
             argv[0]);
      return 0;
    }
    if (fb_ctrl_set_sound_effect(ctrl, &sr, mode)) {
      if (sr.has_success && sr.success)
        printf("Sound effect: %s\n", eq_mode_name(mode));
      else
        printf("Sound effect: set failed\n");
    } else
      printf("no response\n");
    return 0;
  }

  if (!fb_ctrl_get_sound_effect(ctrl, &eq)) {
    printf("no response\n");
    return 0;
  }
  if (eq.has_mode) {
    printf("Sound effect: %s\n", eq_mode_name(eq.mode));
    return 0;
  }
  if (eq.has_status) {
    print_status("Sound effect", eq.status);
    return 0;
  }
  if (eq.mode_count > 0) {
    printf("Sound effect: supported:");
    for (i = 0; i < eq.mode_count; i++)
      printf(" %s", eq_mode_name(eq.modes[i]));
    printf("\n");
    return 0;
  }
  printf("Sound effect: raw=%s\n", eq.raw_hex);
  return 0;
}

static int run_lang(fb_ctrl *ctrl, int argc, char **argv) {
  fb_langres lang;
  fb_setres sr;

  if (argc >= 1) {
    if (!fb_ctrl_set_language(ctrl, &sr, argv[0])) {
      printf("no response\n");
      return 0;
    }
    if (sr.has_success && sr.success)
      printf("Language set to %s\n", argv[0]);
    else if (sr.has_status)
      printf("Language set failed: status=0x%08X\n", sr.status);
    else
      printf("Language set failed\n");
    return 0;
  }

  if (!fb_ctrl_get_language(ctrl, &lang)) {
    printf("no response\n");
    return 0;
  }
  if (lang.tag3[0])
    printf("Available: %s\n", lang.tag3);
  else if (lang.current[0])
    printf("Current: %s\n", lang.current);
  else
    printf("Language setting: (empty)\n");
  return 0;
}

static int hexval(char c) {
  if (c >= '0' && c <= '9')
    return c - '0';
  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;
  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;
  return -1;
}

static int run_raw(fb_ctrl *ctrl, int argc, char **argv) {
  uint8_t buf[256];
  size_t len = 0;
  int i;
  size_t j;
  fb_frames *frames;

  for (i = 0; i < argc && len < sizeof(buf); i++) {
    size_t n = strlen(argv[i]);
    for (j = 0; j < n && len < sizeof(buf); j += 2) {
      int hi, lo;
      if (j + 1 >= n) {
        printf("Error: odd hex length\n");
        return 0;
      }
      hi = hexval(argv[i][j]);
      lo = hexval(argv[i][j + 1]);
      if (hi < 0 || lo < 0) {
        printf("Error: invalid hex '%s'\n", argv[i]);
        return 0;
      }
      buf[len++] = (uint8_t)((hi << 4) | lo);
    }
  }

  frames = fb_ctrl_send(ctrl, buf, len, 2.0);
  if (!frames) {
    printf("no response\n");
    return 0;
  }
  for (i = 0; i < (int)frames->count; i++) {
    size_t k;
    printf("svc=0x%02X cmd=0x%02X data=", frames->items[i].svc,
           frames->items[i].cmd);
    for (k = 0; k < frames->items[i].data_len; k++)
      printf("%02X", frames->items[i].data[k]);
    printf("\n");
  }
  fb_frames_free(frames);
  return 0;
}

static int run_devices(fb_ctrl *ctrl, int argc, char **argv) {
  fb_devices devs;
  fb_setres sr;
  const char *action = argc >= 1 ? argv[0] : "list";
  size_t i;
  char macbuf[24];
  int found;

  if (strcmp(action, "help") == 0 || strcmp(action, "-h") == 0) {
    print_devices_help();
    return 0;
  }

  if (strcmp(action, "list") == 0) {
    if (!fb_ctrl_get_bonded_devices(ctrl, &devs)) {
      printf("no response\n");
      return 0;
    }
    if (devs.count == 0)
      printf("No paired devices reported\n");
    for (i = 0; i < devs.count; i++) {
      fb_device *d = &devs.items[i];
      printf("[%d] %s %s - %s%s\n", d->has_index ? d->index : 255,
             d->name[0] ? d->name : "?", d->addr[0] ? d->addr : "?",
             d->has_conn && d->conn_state ? "Connected" : "Idle",
             d->has_primary && d->primary ? " Primary" : "");
    }
    fb_devices_free(&devs);
    return 0;
  }

  if (argc < 2) {
    printf("Usage: devices %s <mac|idx>\n", action);
    return 0;
  }

  if (strcmp(action, "connect") != 0 && strcmp(action, "disconnect") != 0 &&
      strcmp(action, "unpair") != 0 && strcmp(action, "primary") != 0) {
    printf("Unknown devices action '%s'. Use: devices help\n", action);
    return 0;
  }

  snprintf(macbuf, sizeof(macbuf), "%s", argv[1]);
  if (!fb_valid_mac(macbuf)) {
    found = 0;
    if (fb_ctrl_get_bonded_devices(ctrl, &devs)) {
      int idx = atoi(macbuf);
      for (i = 0; i < devs.count; i++) {
        if (devs.items[i].has_index && devs.items[i].index == idx) {
          snprintf(macbuf, sizeof(macbuf), "%s", devs.items[i].addr);
          found = 1;
          break;
        }
      }
      fb_devices_free(&devs);
    }
    if (!found) {
      printf("Unknown device '%s'\n", argv[1]);
      return 0;
    }
  }

  if (strcmp(action, "primary") == 0) {
    if (fb_ctrl_set_primary_device(ctrl, &sr, macbuf)) {
      if (sr.has_success && sr.success)
        printf("Primary device: %s\n", macbuf);
      else
        printf("Set primary failed: raw=%s\n", sr.raw_hex);
    } else
      printf("no response\n");
    return 0;
  }

  if (!fb_ctrl_single_device_setting(ctrl, &sr,
                                     strcmp(action, "connect") == 0      ? 1
                                     : strcmp(action, "disconnect") == 0 ? 2
                                                                         : 3,
                                     macbuf)) {
    printf("no response\n");
    return 0;
  }

  if (sr.has_result_code) {
    int code = sr.result_code;
    if (code == 0 || code == (int)FB_STATUS_OK)
      printf("%s %s\n",
             strcmp(action, "connect") == 0      ? "Connected"
             : strcmp(action, "disconnect") == 0 ? "Disconnected"
                                                 : "Unpaired",
             macbuf);
    else
      printf("%s failed: result=%d\n",
             strcmp(action, "connect") == 0      ? "Connect"
             : strcmp(action, "disconnect") == 0 ? "Disconnect"
                                                 : "Unpair",
             code);
  } else if (sr.has_success) {
    printf("%s %s\n",
           strcmp(action, "connect") == 0      ? "Connected"
           : strcmp(action, "disconnect") == 0 ? "Disconnected"
                                               : "Unpaired",
           macbuf);
  } else if (sr.has_status) {
    printf("%s failed: status=0x%08X\n",
           strcmp(action, "connect") == 0      ? "Connect"
           : strcmp(action, "disconnect") == 0 ? "Disconnect"
                                               : "Unpair",
           sr.status);
  } else
    printf("%s failed\n", strcmp(action, "connect") == 0      ? "Connect"
                          : strcmp(action, "disconnect") == 0 ? "Disconnect"
                                                              : "Unpair");
  return 0;
}

static int run_info(fb_ctrl *ctrl) {
  fb_battery bat;
  fb_version ver;
  fb_eqres eq;
  fb_langres lang;
  size_t i;

  if (fb_ctrl_get_battery(ctrl, &bat))
    printf("battery: L:%d%%  R:%d%%  Box:%d%%\n", bat.left_battery,
           bat.right_battery, bat.box_battery);
  else
    printf("battery: (no response)\n");

  if (fb_ctrl_get_version(ctrl, &ver)) {
    if (ver.has_model)
      printf("model: %s\n", ver.model);
    if (ver.has_firmware)
      printf("firmware: %s\n", ver.firmware);
    if (ver.has_serial)
      printf("serial: %s\n", ver.serial);
    if (ver.has_bt_version)
      printf("bt_version: %s\n", ver.bt_version);
    if (ver.has_bt_prefix)
      printf("bt_prefix: %s\n", ver.bt_prefix);
    if (ver.has_bud_serials)
      printf("bud_serials: %s\n", ver.bud_serials);
    for (i = 0; i < ver.other_count; i++)
      printf("field_%d: %s\n", ver.other_tags[i], ver.other[i]);
  } else
    printf("version: (no response)\n");

  for (i = 0; i < FB_GESTURE_COUNT; i++) {
    fb_touchres tr;
    char buf[64];
    if (!fb_ctrl_get_touch(ctrl, &tr, &FB_GESTURES[i])) {
      printf("%s: (no response)\n", FB_GESTURES[i].key);
      continue;
    }
    if (tr.has_status) {
      print_status(FB_GESTURES[i].key, tr.status);
      continue;
    }
    printf("%s: ", FB_GESTURES[i].key);
    if (tr.has_left)
      printf("Left=%s", action_name((int)i, tr.left, buf, sizeof(buf)));
    else
      printf("Left=unset");
    if (tr.has_right)
      printf(", Right=%s\n", action_name((int)i, tr.right, buf, sizeof(buf)));
    else
      printf(", Right=unset\n");
  }

  {
    int assigned = 0;
    printf("noise_control: ");
    for (i = 0; i < FB_GESTURE_COUNT; i++) {
      fb_touchres tr;
      int nc = FB_GESTURES[i].nc_action;
      if (nc < 0)
        continue;
      if (fb_ctrl_get_touch(ctrl, &tr, &FB_GESTURES[i])) {
        if (tr.has_left && tr.left == nc) {
          printf("%s(Left) ", FB_GESTURES[i].key);
          assigned = 1;
        }
        if (tr.has_right && tr.right == nc) {
          printf("%s(Right) ", FB_GESTURES[i].key);
          assigned = 1;
        }
      }
    }
    if (!assigned)
      printf("(none)");
    printf("\n");
  }

  {
    fb_ancres a;
    const char *anc_name = NULL;
    if (fb_ctrl_get_anc_state(ctrl, &a) && a.has_mode)
      anc_name = nc_mode_name(a.mode);
    else if (fb_ctrl_query_nr_mode(ctrl, &a) && a.has_mode)
      anc_name = nc_mode_name(a.mode);
    else if (fb_ctrl_get_anc_mode_level(ctrl, &a) && a.has_mode)
      anc_name = nc_mode_name(a.mode);
    printf("anc: %s\n", anc_name ? anc_name : "(no response)");
  }

  if (fb_ctrl_get_sound_effect(ctrl, &eq)) {
    if (eq.has_mode)
      printf("sound_effect: %s\n", eq_mode_name(eq.mode));
    else if (eq.has_status)
      print_status("sound_effect", eq.status);
    else
      printf("sound_effect: raw=%s\n", eq.raw_hex);
  } else
    printf("sound_effect: (no response)\n");

  if (fb_ctrl_get_language(ctrl, &lang)) {
    if (lang.tag3[0])
      printf("language: %s\n", lang.tag3);
    else if (lang.current[0])
      printf("language: %s\n", lang.current);
    else
      printf("language: (empty)\n");
  } else
    printf("language: (no response)\n");

  for (i = 0; i < FB_FEATURABLE_COUNT; i++) {
    fb_boolres br;
    if (fb_ctrl_get_bool(ctrl, &br, FB_FEATURABLE[i].get,
                         FB_FEATURABLE[i].get_len, FB_FEATURABLE[i].svc,
                         FB_FEATURABLE[i].cmd, FB_FEATURABLE[i].set_cmd)) {
      if (br.has_enabled)
        printf("%s: %s\n", FB_FEATURABLE[i].key, br.enabled ? "On" : "Off");
      else if (br.has_status)
        print_status(FB_FEATURABLE[i].key, br.status);
      else
        printf("%s: raw=%s\n", FB_FEATURABLE[i].key, br.raw_hex);
    } else
      printf("%s: (no response)\n", FB_FEATURABLE[i].key);
  }

  return 0;
}

static int is_known_command(const char *s) {
  static const char *const cmds[] = {
      "help", "bat",   "ver", "info",   "gesture", "anc",   "nc",
      "sfx",  "lang",  "raw", "misc",   "devices", "dev",   "lp",
      "sp",   "slide", "dc",  "triple", "pinch",   "lhold",
  };
  size_t i;
  for (i = 0; i < sizeof(cmds) / sizeof(cmds[0]); i++) {
    if (strcmp(s, cmds[i]) == 0)
      return 1;
  }
  return 0;
}

static int is_gesture_command(const char *s) {
  return strcmp(s, "lp") == 0 || strcmp(s, "sp") == 0 ||
         strcmp(s, "slide") == 0 || strcmp(s, "dc") == 0 ||
         strcmp(s, "triple") == 0 || strcmp(s, "pinch") == 0 ||
         strcmp(s, "lhold") == 0;
}

int fb_cmd_run(const char *address, double timeout, int argc, char **argv) {
  char mac[32];
  const char *resolved;
  fb_ctrl ctrl;
  char **tokens = NULL;
  size_t ntok = 0, tcap = 0;
  size_t i, j;

  (void)timeout;

  if (argc == 0 || strcmp(argv[0], "--help") == 0 ||
      strcmp(argv[0], "-h") == 0) {
    print_run_help();
    return 0;
  }

  resolved = resolve_address(address, mac, sizeof(mac));
  if (!resolved)
    return 0;

  if (!fb_ctrl_connect(&ctrl, resolved, FB_SPP_CHANNEL)) {
    printf("Connect failed\n");
    return 0;
  }

  for (i = 0; i < (size_t)argc; i++) {
    char *copy = strdup(argv[i]);
    char *tok = strtok(copy, " \t");
    while (tok) {
      if (ntok == tcap) {
        tcap = tcap ? tcap * 2 : 32;
        tokens = realloc(tokens, tcap * sizeof(char *));
      }
      tokens[ntok++] = strdup(tok);
      tok = strtok(NULL, " \t");
    }
    free(copy);
  }

  i = 0;
  while (i < ntok) {
    const char *cmd = tokens[i];
    j = i + 1;
    while (j < ntok && !is_known_command(tokens[j]))
      j++;

    if (strcmp(cmd, "gesture") == 0) {
      if (j - (i + 1) > 0)
        run_gesture(&ctrl, (int)(j - i - 1), tokens + i + 1);
      else
        run_gesture(&ctrl, (int)(ntok - j), tokens + j);
      break;
    }
    if (is_gesture_command(cmd)) {
      run_gesture(&ctrl, (int)(j - i), tokens + i);
      break;
    }

    if (strcmp(cmd, "help") == 0)
      print_run_help();
    else if (strcmp(cmd, "bat") == 0) {
      fb_battery bat;
      if (fb_ctrl_get_battery(&ctrl, &bat))
        printf("L:%d%%  R:%d%%  Box:%d%%\n", bat.left_battery,
               bat.right_battery, bat.box_battery);
      else
        printf("no response\n");
    } else if (strcmp(cmd, "ver") == 0) {
      fb_version ver;
      if (fb_ctrl_get_version(&ctrl, &ver)) {
        if (ver.has_model)
          printf("model: %s\n", ver.model);
        if (ver.has_firmware)
          printf("firmware: %s\n", ver.firmware);
        if (ver.has_serial)
          printf("serial: %s\n", ver.serial);
        if (ver.has_bt_version)
          printf("bt_version: %s\n", ver.bt_version);
        if (ver.has_bt_prefix)
          printf("bt_prefix: %s\n", ver.bt_prefix);
        if (ver.has_bud_serials)
          printf("bud_serials: %s\n", ver.bud_serials);
      } else
        printf("no response\n");
    } else if (strcmp(cmd, "info") == 0)
      run_info(&ctrl);
    else if (strcmp(cmd, "anc") == 0 || strcmp(cmd, "nc") == 0)
      run_anc(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else if (strcmp(cmd, "sfx") == 0)
      run_sfx(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else if (strcmp(cmd, "lang") == 0)
      run_lang(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else if (strcmp(cmd, "misc") == 0)
      run_misc(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else if (strcmp(cmd, "devices") == 0 || strcmp(cmd, "dev") == 0)
      run_devices(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else if (strcmp(cmd, "raw") == 0)
      run_raw(&ctrl, (int)(j - i - 1), tokens + i + 1);
    else
      printf("Unknown: %s\n", cmd);

    i = j;
    if (i < ntok)
      printf("\n");
  }

  for (i = 0; i < ntok; i++)
    free(tokens[i]);
  free(tokens);

  fb_ctrl_disconnect(&ctrl);
  return 0;
}
