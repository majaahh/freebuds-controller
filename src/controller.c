/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <bluetooth/bluetooth.h>
#include <bluetooth/rfcomm.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include "controller.h"
#include "crc16.h"

static const char *HEX = "0123456789ABCDEF";

void fb_hexdump(const uint8_t *data, size_t len, char *out, size_t outsz) {
  size_t i;
  if (outsz == 0)
    return;
  for (i = 0; i < len && outsz > 3; i++) {
    *out++ = HEX[data[i] >> 4];
    *out++ = HEX[data[i] & 0xF];
    outsz -= 2;
  }
  if (outsz > 0)
    *out = '\0';
}

static void set_timeout(int sock, double timeout) {
  struct timeval tv;
  tv.tv_sec = (long)timeout;
  tv.tv_usec = (long)((timeout - (double)tv.tv_sec) * 1e6);
  setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
}

int fb_ctrl_connect(fb_ctrl *c, const char *mac, int channel) {
  struct sockaddr_rc addr;

  memset(c, 0, sizeof(*c));
  if (!mac)
    return 0;
  snprintf(c->mac, sizeof(c->mac), "%s", mac);

  c->sock = socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM);
  if (c->sock < 0)
    return 0;

  set_timeout(c->sock, 10.0);
  memset(&addr, 0, sizeof(addr));
  addr.rc_family = AF_BLUETOOTH;
  addr.rc_channel = (uint8_t)channel;
  str2ba(mac, &addr.rc_bdaddr);

  if (connect(c->sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
    close(c->sock);
    c->sock = -1;
    return 0;
  }

  c->connected = 1;
  return 1;
}

void fb_ctrl_disconnect(fb_ctrl *c) {
  if (c->sock >= 0) {
    close(c->sock);
    c->sock = -1;
  }
  c->connected = 0;
}

fb_frames *fb_ctrl_send(fb_ctrl *c, const uint8_t *cmd, size_t cmd_len,
                        double timeout) {
  fb_frames *frames;
  uint8_t *frame;
  size_t frame_len;
  uint8_t *response = NULL;
  size_t response_len = 0, response_cap = 0;

  if (!c->connected || c->sock < 0)
    return NULL;

  frame = fb_build_frame(cmd, cmd_len, &frame_len);
  if (!frame)
    return NULL;

  if (send(c->sock, frame, frame_len, 0) < 0) {
    free(frame);
    c->connected = 0;
    return NULL;
  }
  free(frame);

  set_timeout(c->sock, timeout);
  for (;;) {
    uint8_t chunk[4096];
    ssize_t n = recv(c->sock, chunk, sizeof(chunk), 0);
    if (n <= 0)
      break;
    if (response_len + (size_t)n > response_cap) {
      response_cap = response_len + (size_t)n + 4096;
      response = realloc(response, response_cap);
    }
    memcpy(response + response_len, chunk, (size_t)n);
    response_len += (size_t)n;
  }

  if (response_len == 0) {
    free(response);
    return NULL;
  }

  frames = fb_parse_frames(response, response_len);
  free(response);
  return frames;
}

static const fb_frame *match_frame(const fb_frames *frames, int svc, int cmd) {
  size_t i;
  if (!frames)
    return NULL;
  for (i = 0; i < frames->count; i++) {
    if (frames->items[i].svc == svc && frames->items[i].cmd == cmd)
      return &frames->items[i];
  }
  return NULL;
}

static const fb_frame *match_frame_or_first(const fb_frames *frames, int svc,
                                            int cmd) {
  const fb_frame *f = match_frame(frames, svc, cmd);
  if (!f && frames && frames->count > 0)
    return &frames->items[0];
  return f;
}

static int is_status_response(const uint8_t *data, size_t len) {
  return len >= 6 && data[0] == 0x7F && data[1] == 0x04;
}

static uint32_t parse_status_code(const uint8_t *data, size_t len) {
  if (is_status_response(data, len))
    return ((uint32_t)data[2] << 24) | ((uint32_t)data[3] << 16) |
           ((uint32_t)data[4] << 8) | data[5];
  return 0;
}

static int extract_byte_at(const uint8_t *data, size_t len, size_t offset,
                           uint8_t *out) {
  if (offset < len) {
    *out = data[offset];
    return 1;
  }
  return 0;
}

static const uint8_t *tlv_value(const fb_tlvs *tlvs, uint8_t tag,
                                size_t *vlen) {
  size_t i;
  for (i = 0; i < tlvs->count; i++) {
    if (tlvs->items[i].tag == tag) {
      if (vlen)
        *vlen = tlvs->items[i].len;
      return tlvs->items[i].value;
    }
  }
  return NULL;
}

static void set_raw_hex(char *out, size_t outsz, const uint8_t *data,
                        size_t len) {
  fb_hexdump(data, len, out, outsz);
}

int fb_ctrl_get_battery(fb_ctrl *c, fb_battery *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  const uint8_t *val;
  size_t vlen;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_BATTERY, sizeof(FB_CMD_BATTERY), 2.0);
  f = match_frame(frames, 0x01, 0x08);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  val = tlv_value(&tlvs, 2, &vlen);
  if (val && vlen >= 3) {
    out->left_battery = val[0];
    out->right_battery = val[1];
    out->box_battery = val[2];
    fb_tlvs_free(&tlvs);
    fb_frames_free(frames);
    return 1;
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 0;
}

static void decode_version_string(const uint8_t *v, size_t vlen, char *out,
                                  size_t outsz) {
  size_t i, n = 0;
  for (i = 0; i < vlen && n + 1 < outsz; i++) {
    unsigned char ch = v[i];
    if (ch == 0)
      break;
    if (ch >= 0x20 && ch < 0x7F)
      out[n++] = (char)ch;
  }
  out[n] = '\0';
}

int fb_ctrl_get_version(fb_ctrl *c, fb_version *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_VERSION, FB_CMD_VERSION_LEN, 2.0);
  f = match_frame(frames, 0x01, 0x07);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    char buf[128];
    char *dst = NULL;
    int *has = NULL;

    decode_version_string(t->value, t->len, buf, sizeof(buf));
    if (!buf[0])
      continue;
    switch (t->tag) {
    case 3:
      dst = out->model;
      has = &out->has_model;
      break;
    case 7:
      dst = out->firmware;
      has = &out->has_firmware;
      break;
    case 9:
      dst = out->serial;
      has = &out->has_serial;
      break;
    case 10:
      dst = out->bt_version;
      has = &out->has_bt_version;
      break;
    case 15:
      dst = out->bt_prefix;
      has = &out->has_bt_prefix;
      break;
    case 24:
      dst = out->bud_serials;
      has = &out->has_bud_serials;
      break;
    default:
      if (out->other_count < 8) {
        snprintf(out->other[out->other_count], sizeof(out->other[0]), "%s",
                 buf);
        out->other_tags[out->other_count] = t->tag;
        out->other_count++;
      }
      continue;
    }
    if (dst && strlen(buf) < 100) {
      snprintf(dst, 100, "%s", buf);
      if (has)
        *has = 1;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_bool(fb_ctrl *c, fb_boolres *out, const uint8_t *get_cmd,
                     size_t get_len, int svc, int get_cmd_id, int set_cmd_id) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  uint8_t b;
  size_t i;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, get_cmd, get_len, 2.0);
  f = match_frame(frames, svc, get_cmd_id);
  if (!f)
    f = match_frame(frames, svc, set_cmd_id);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = out->status == FB_STATUS_OK;
    fb_frames_free(frames);
    return 1;
  }

  if (extract_byte_at(f->data, f->data_len, 2, &b) && (b == 0 || b == 1)) {
    out->has_enabled = 1;
    out->enabled = b == 1;
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    if (tlvs.items[i].len == 1 &&
        (tlvs.items[i].value[0] == 0 || tlvs.items[i].value[0] == 1)) {
      out->has_enabled = 1;
      out->enabled = tlvs.items[i].value[0] == 1;
      fb_tlvs_free(&tlvs);
      fb_frames_free(frames);
      return 1;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_bool(fb_ctrl *c, fb_setres *out, const uint8_t *set_cmd,
                     size_t set_len, int svc, int set_cmd_id) {
  fb_frames *frames;
  const fb_frame *f;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, set_cmd, set_len, 2.0);
  f = match_frame(frames, svc, set_cmd_id);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
    fb_frames_free(frames);
    return 1;
  }

  out->success = 1;
  out->has_success = 1;
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_uint(fb_ctrl *c, fb_uintres *out, const uint8_t *cmd,
                     size_t len, int svc, int cmd_id) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  const uint8_t *val;
  size_t vlen, i;
  uint32_t v = 0;
  uint8_t b;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, cmd, len, 2.0);
  f = match_frame(frames, svc, cmd_id);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = out->status == FB_STATUS_OK;
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  val = tlv_value(&tlvs, 1, &vlen);
  if (val) {
    for (i = 0; i < vlen; i++)
      v = (v << 8) | val[i];
    out->has_value = 1;
    out->value = v;
    fb_tlvs_free(&tlvs);
    fb_frames_free(frames);
    return 1;
  }
  fb_tlvs_free(&tlvs);

  if (extract_byte_at(f->data, f->data_len, 2, &b)) {
    out->has_value = 1;
    out->value = b;
    fb_frames_free(frames);
    return 1;
  }

  fb_frames_free(frames);
  return 1;
}

static int in_nc_modes(int v) { return v == 0 || v == 1 || v == 2; }

int fb_ctrl_get_touch(fb_ctrl *c, fb_touchres *out, const fb_gesture *g) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, g->get, g->get_len, 2.0);
  f = match_frame(frames, g->svc, g->cmd);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = out->status == FB_STATUS_OK;
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    size_t j;
    if (t->tag == 1 && t->len == 1) {
      out->left = t->value[0];
      out->has_left = 1;
    } else if (t->tag == 2 && t->len == 1) {
      out->right = t->value[0];
      out->has_right = 1;
    } else if (t->tag == 3) {
      for (j = 0; j < t->len && out->supported_count < 32; j++) {
        if (t->value[j] != 0xFF)
          out->supported[out->supported_count++] = t->value[j];
      }
    } else if (t->tag == 4 && t->len == 1) {
      out->call_left = t->value[0];
      out->has_call_left = 1;
    } else if (t->tag == 5 && t->len == 1) {
      out->call_right = t->value[0];
      out->has_call_right = 1;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

static uint8_t *gesture_set_payload(const fb_gesture *g, int side, int action,
                                    size_t *len) {
  int left = (side == FB_SIDE_LEFT) ? action : -1;
  int right = (side == FB_SIDE_RIGHT) ? action : -1;

  if (strcmp(g->key, "long_press") == 0)
    return fb_cmd_set_long_press_mbb(left, right, len);
  if (strcmp(g->key, "pinch") == 0)
    return fb_cmd_set_pinch(left, right, len);
  if (strcmp(g->key, "slide") == 0)
    return fb_cmd_set_slide_mbb(left, right, len);
  if (strcmp(g->key, "double_click") == 0)
    return fb_cmd_set_double_click_mbb(left, right, len);
  if (strcmp(g->key, "triple_click") == 0)
    return fb_cmd_set_triple_click(left, right, len);
  if (strcmp(g->key, "light_hold") == 0)
    return fb_cmd_set_light_hold(left, right, len);
  return NULL;
}

int fb_ctrl_set_touch(fb_ctrl *c, fb_setres *out, const fb_gesture *g, int side,
                      int action) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  uint8_t *payload;
  size_t payload_len;
  size_t i;
  uint8_t resp;

  memset(out, 0, sizeof(*out));
  payload = gesture_set_payload(g, side, action, &payload_len);
  if (!payload)
    return 0;
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame_or_first(frames, g->svc, g->set_cmd);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if ((t->tag == 3 || t->tag == 6) && t->len == 1) {
      out->result_code = t->value[0];
      out->has_result_code = 1;
      out->success = (t->value[0] == 0 || t->value[0] == 2);
      out->has_success = 1;
      snprintf(out->result_name, sizeof(out->result_name), "Result %d",
               t->value[0]);
      fb_tlvs_free(&tlvs);
      fb_frames_free(frames);
      return 1;
    }
  }
  fb_tlvs_free(&tlvs);

  if (extract_byte_at(f->data, f->data_len, 2, &resp)) {
    out->success = resp == (uint8_t)action;
    out->has_success = 1;
    fb_frames_free(frames);
    return 1;
  }

  fb_frames_free(frames);
  return 1;
}

static void anc_set_from_status(fb_setres *out, const uint8_t *data,
                                size_t len) {
  fb_tlvs tlvs;
  const uint8_t *val;
  size_t vlen;

  if (is_status_response(data, len)) {
    out->has_status = 1;
    out->status = parse_status_code(data, len);
    out->success = (out->status == 0 || out->status == FB_STATUS_OK);
    out->has_success = 1;
    return;
  }

  tlvs = fb_parse_tlv(data, len);
  val = tlv_value(&tlvs, 2, &vlen);
  if (val && vlen == 1) {
    out->has_status = 1;
    out->status = val[0];
    out->success = (val[0] == 0);
    out->has_success = 1;
  }
  fb_tlvs_free(&tlvs);
}

int fb_ctrl_set_anc_state(fb_ctrl *c, fb_setres *out, int mode) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_anc_state(mode, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame_or_first(frames, 0x2B, 0x04);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }
  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);
  anc_set_from_status(out, f->data, f->data_len);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_anc_state_extended(fb_ctrl *c, fb_setres *out, int mode,
                                   int level) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_anc_state_level(mode, level, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame_or_first(frames, 0x2B, 0x04);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }
  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);
  anc_set_from_status(out, f->data, f->data_len);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_anc_level(fb_ctrl *c, fb_setres *out, int level) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_anc_level(level, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame(frames, 0x2B, 0x08);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }
  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);
  anc_set_from_status(out, f->data, f->data_len);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_noise_control(fb_ctrl *c, fb_setres *out, int mode, int value) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_noise_control(mode, value, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame(frames, 0x2B, 0x18);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }
  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);
  anc_set_from_status(out, f->data, f->data_len);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_noise_mode(fb_ctrl *c, fb_setres *out, int mode) {
  fb_setres r1, r2;
  int got = fb_ctrl_set_anc_state(c, &r1, mode);
  if (got) {
    if (r1.has_success && r1.success) {
      *out = r1;
      return 1;
    }
    fb_ctrl_set_anc_state_extended(c, &r2, mode, mode == 0 ? 0x00 : 0xFF);
    if (r2.has_success && r2.success) {
      *out = r2;
      return 1;
    }
    *out = r1;
    return 1;
  }
  memset(out, 0, sizeof(*out));
  return 0;
}

int fb_ctrl_get_anc_state(fb_ctrl *c, fb_ancres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  const uint8_t *val;
  size_t vlen;
  uint8_t b;

  memset(out, 0, sizeof(*out));
  snprintf(out->source, sizeof(out->source), "anc_state");
  frames =
      fb_ctrl_send(c, FB_CMD_GET_ANC_STATE, sizeof(FB_CMD_GET_ANC_STATE), 2.0);
  f = match_frame(frames, 0x2B, 0x05);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = (out->status == 0 || out->status == FB_STATUS_OK);
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  val = tlv_value(&tlvs, 1, &vlen);
  if (val && vlen >= 1) {
    int mode = (vlen == 1) ? val[0] : val[1];
    if (in_nc_modes(mode)) {
      out->has_mode = 1;
      out->mode = mode;
      if (vlen == 2) {
        out->has_level = 1;
        out->level = val[0];
      }
      fb_tlvs_free(&tlvs);
      fb_frames_free(frames);
      return 1;
    }
  }
  if (tlvs.count == 0 && extract_byte_at(f->data, f->data_len, 2, &b) &&
      in_nc_modes(b)) {
    out->has_mode = 1;
    out->mode = b;
    fb_tlvs_free(&tlvs);
    fb_frames_free(frames);
    return 1;
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_anc_mode_level(fb_ctrl *c, fb_ancres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  snprintf(out->source, sizeof(out->source), "anc_mode_level");
  frames = fb_ctrl_send(c, FB_CMD_GET_ANC_MODE_LEVEL,
                        sizeof(FB_CMD_GET_ANC_MODE_LEVEL), 2.0);
  f = match_frame(frames, 0x2B, 0x07);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 1 && t->len == 1) {
      out->has_mode = 1;
      out->mode = t->value[0];
    } else if (t->tag == 2 && t->len == 1) {
      out->has_common_index = 1;
      out->common_index = t->value[0];
    } else if (t->tag == 3 && t->len == 1) {
      out->has_plane_index = 1;
      out->plane_index = t->value[0];
    } else if (t->tag == 4 && t->len == 1) {
      out->has_fly_mode = 1;
      out->fly_mode = t->value[0];
    } else if (t->tag == 5 && t->len == 2) {
      out->has_mode_scene = 1;
      out->mode_scene = t->value[0];
      out->has_mode_voice = 1;
      out->mode_voice = t->value[1] & 0x03;
      out->has_mode_noise = 1;
      out->mode_noise = (t->value[1] & 0x3C) >> 2;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_query_nr_mode(fb_ctrl *c, fb_ancres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  snprintf(out->source, sizeof(out->source), "query_nr_mode");
  frames = fb_ctrl_send(c, FB_CMD_QUERY_NOISE_REDUCTION_MODE,
                        sizeof(FB_CMD_QUERY_NOISE_REDUCTION_MODE), 2.0);
  f = match_frame(frames, 0x2B, 0x2A);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 1 && t->len == 2) {
      out->has_level = 1;
      out->level = t->value[0];
      out->has_mode = 1;
      out->mode = t->value[1];
    } else if (t->tag == 2 && t->len == 1) {
      out->has_extra = 1;
      out->extra = t->value[0];
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_noise_control_lr(fb_ctrl *c, fb_ancres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  snprintf(out->source, sizeof(out->source), "noise_control_lr");
  frames = fb_ctrl_send(c, FB_CMD_GET_NOISE_CONTROL,
                        sizeof(FB_CMD_GET_NOISE_CONTROL), 2.0);
  f = match_frame(frames, 0x2B, 0x19);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 1 && t->len == 1) {
      out->has_mode_scene = 1;
      out->mode_scene = t->value[0];
    } else if (t->tag == 2 && t->len == 1) {
      out->has_mode_voice = 1;
      out->mode_voice = t->value[0];
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_sound_effect(fb_ctrl *c, fb_eqres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i, j;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_GET_EQ, sizeof(FB_CMD_GET_EQ), 2.0);
  f = match_frame(frames, 0x2B, 0x4A);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = (out->status == 0 || out->status == FB_STATUS_OK);
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 1 && t->len == 1) {
      out->has_support = 1;
      out->support = t->value[0] == 1;
    } else if (t->tag == 2 && t->len == 1) {
      out->has_mode = 1;
      out->mode = t->value[0];
    } else if (t->tag == 3) {
      for (j = 0; j < t->len && out->mode_count < 16; j++) {
        if (t->value[j] != 0xFF)
          out->modes[out->mode_count++] = t->value[j];
      }
    } else if (t->tag == 4 && t->len == 1) {
      out->has_recommended = 1;
      out->recommended = t->value[0];
    } else if (t->tag == 8) {
      set_raw_hex(out->custom_hex, sizeof(out->custom_hex), t->value, t->len);
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_sound_effect(fb_ctrl *c, fb_setres *out, int mode) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_eq(mode, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame(frames, 0x2B, 0x49);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = (out->status == 0 || out->status == FB_STATUS_OK);
    out->has_success = 1;
  }
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_language(fb_ctrl *c, fb_langres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;
  char buf[512];

  memset(out, 0, sizeof(*out));
  frames =
      fb_ctrl_send(c, FB_CMD_GET_LANGUAGE, sizeof(FB_CMD_GET_LANGUAGE), 2.0);
  f = match_frame(frames, 0x0C, 0x02);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    decode_version_string(t->value, t->len, buf, sizeof(buf));
    if (t->tag == 1) {
      if (buf[0])
        snprintf(out->current, sizeof(out->current), "%.127s", buf);
    } else if (t->tag == 2 && t->len == 1) {
      out->has_unit = 1;
      out->unit = t->value[0];
    } else if (t->tag == 3) {
      if (buf[0])
        snprintf(out->tag3, sizeof(out->tag3), "%s", buf);
    } else if (buf[0] && out->other_count < 8) {
      snprintf(out->other[out->other_count], sizeof(out->other[0]), "%.127s",
               buf);
      out->other_tags[out->other_count] = t->tag;
      out->other_count++;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_language(fb_ctrl *c, fb_setres *out, const char *lang) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;
  size_t i;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_language(lang, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);

  f = match_frame(frames, 0x0C, 0x01);
  if (!f && frames) {
    for (i = 0; i < frames->count; i++) {
      if (frames->items[i].svc == 0x0C) {
        f = &frames->items[i];
        break;
      }
    }
  }
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
  } else {
    out->success = 1;
    out->has_success = 1;
  }
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_wearing_status(fb_ctrl *c, fb_wearres *out) {
  fb_frames *frames;
  const fb_frame *f;
  fb_tlvs tlvs;
  size_t i;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_GET_WEARING_STATUS,
                        sizeof(FB_CMD_GET_WEARING_STATUS), 2.0);
  f = match_frame(frames, 0x2B, 0x25);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->status_ok = out->status == FB_STATUS_OK;
    fb_frames_free(frames);
    return 1;
  }

  tlvs = fb_parse_tlv(f->data, f->data_len);
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 1 && t->len == 1) {
      out->has_left_ear = 1;
      out->left_ear = t->value[0];
      out->left_in = t->value[0] == 1;
    } else if (t->tag == 2 && t->len == 1) {
      out->has_right_ear = 1;
      out->right_ear = t->value[0];
      out->right_in = t->value[0] == 1;
    }
  }
  fb_tlvs_free(&tlvs);
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_set_dormant_time(fb_ctrl *c, fb_setres *out, int option,
                             int seconds) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  payload = fb_cmd_set_dormant_time(option, seconds, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  f = match_frame(frames, 0x2B, 0x47);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
  } else {
    out->success = 1;
    out->has_success = 1;
  }
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_start_pair(fb_ctrl *c, fb_setres *out) {
  fb_frames *frames;
  const fb_frame *f;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_STATE_PAIR, sizeof(FB_CMD_STATE_PAIR), 2.0);
  f = match_frame(frames, 0x2B, 0x90);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
  } else {
    out->success = 1;
    out->has_success = 1;
  }
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_exit_fit_check(fb_ctrl *c, fb_setres *out) {
  fb_frames *frames;
  const fb_frame *f;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_EXIT_FIT_CHECK, sizeof(FB_CMD_EXIT_FIT_CHECK),
                        2.0);
  f = match_frame(frames, 0x2B, 0x26);
  if (!f) {
    fb_frames_free(frames);
    return 0;
  }

  set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);

  if (is_status_response(f->data, f->data_len)) {
    out->has_status = 1;
    out->status = parse_status_code(f->data, f->data_len);
    out->success = out->status == FB_STATUS_OK;
    out->has_success = 1;
  } else {
    out->success = 1;
    out->has_success = 1;
  }
  fb_frames_free(frames);
  return 1;
}

static void parse_bonded_device(const uint8_t *data, size_t len,
                                fb_device *dev) {
  fb_tlvs tlvs = fb_parse_tlv(data, len);
  size_t i;
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    if (t->tag == 2 && t->len == 1) {
      dev->number = t->value[0];
      dev->has_number = 1;
    } else if (t->tag == 3 && t->len == 1) {
      dev->index = t->value[0];
      dev->has_index = 1;
    } else if (t->tag == 4 && t->len == 6) {
      fb_mac_to_str(t->value, dev->addr);
    } else if (t->tag == 5 && t->len == 1) {
      dev->conn_state = t->value[0] & 1;
      dev->business_state = (t->value[0] & 0x0E) >> 1;
      dev->in_business = dev->business_state > 1;
      dev->has_conn = 1;
    } else if (t->tag == 6 && t->len == 1) {
      dev->type = t->value[0];
      dev->has_type = 1;
    } else if (t->tag == 7 && t->len == 1) {
      dev->primary = t->value[0];
      dev->has_primary = 1;
    } else if (t->tag == 8 && t->len == 1) {
      dev->back_conn_permit = t->value[0];
      dev->has_back_conn = 1;
    } else if (t->tag == 9 && t->len > 0) {
      decode_version_string(t->value, t->len, dev->name, sizeof(dev->name));
    } else if (t->tag == 10 && t->len == 1) {
      dev->allow_audio_auto_switch = t->value[0] == 1;
      dev->has_aas = 1;
    } else if (t->tag == 11 && t->len == 1) {
      dev->nearlink = t->value[0] == 1;
      dev->has_nearlink = 1;
    } else if ((t->tag == 13 || t->tag == 15) && t->len == 1) {
      dev->lock_channel = t->value[0] == 1;
      dev->has_lock = 1;
    }
  }
  fb_tlvs_free(&tlvs);
}

static void parse_device_report(const uint8_t *data, size_t len, fb_device *dev,
                                char *addr_out, size_t addr_sz, int *type) {
  fb_tlvs tlvs = fb_parse_tlv(data, len);
  size_t i;
  *type = -1;
  if (addr_out && addr_sz > 0)
    addr_out[0] = '\0';
  for (i = 0; i < tlvs.count; i++) {
    fb_tlv *t = &tlvs.items[i];
    *type = t->tag;
    if (t->tag == 2 && t->len == 6) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
    } else if (t->tag == 4 && t->len == 6) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
    } else if (t->tag == 5 && t->len == 7) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
      dev->conn_state = t->value[6] & 1;
      dev->business_state = (t->value[6] & 0x0E) >> 1;
      dev->in_business = dev->business_state > 1;
      dev->has_conn = 1;
    } else if (t->tag == 6 && t->len == 7) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
      dev->back_conn_permit = t->value[6];
      dev->has_back_conn = 1;
    } else if (t->tag == 7 && t->len == 6) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
    } else if (t->tag == 8 && t->len == 7) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
      dev->allow_audio_auto_switch = t->value[6] == 1;
      dev->has_aas = 1;
    } else if (t->tag == 9 && t->len == 7) {
      if (addr_out)
        fb_mac_to_str(t->value, addr_out);
      dev->lock_channel = t->value[6] == 1;
      dev->has_lock = 1;
    }
  }
  fb_tlvs_free(&tlvs);
}

static fb_device *find_device(fb_devices *devs, const char *addr) {
  size_t i;
  for (i = 0; i < devs->count; i++) {
    if (strcmp(devs->items[i].addr, addr) == 0)
      return &devs->items[i];
  }
  return NULL;
}

static void sort_devices_by_index(fb_devices *devs) {
  size_t i, j;
  for (i = 0; i < devs->count; i++) {
    for (j = i + 1; j < devs->count; j++) {
      int ai = devs->items[i].has_index ? devs->items[i].index : 255;
      int bi = devs->items[j].has_index ? devs->items[j].index : 255;
      if (bi < ai) {
        fb_device tmp = devs->items[i];
        devs->items[i] = devs->items[j];
        devs->items[j] = tmp;
      }
    }
  }
}

int fb_ctrl_get_bonded_devices(fb_ctrl *c, fb_devices *out) {
  fb_frames *frames;
  size_t i;

  memset(out, 0, sizeof(*out));
  frames = fb_ctrl_send(c, FB_CMD_GET_DEVICES_BONDED,
                        sizeof(FB_CMD_GET_DEVICES_BONDED), 2.0);
  if (!frames)
    return 0;

  for (i = 0; i < frames->count; i++) {
    fb_frame *fr = &frames->items[i];
    if (fr->svc != 0x2B)
      continue;
    if (fr->cmd == 0x31) {
      fb_device *dev = NULL;
      char addr[24] = "";
      fb_tlvs tlvs = fb_parse_tlv(fr->data, fr->data_len);
      size_t j;
      for (j = 0; j < tlvs.count; j++) {
        if (tlvs.items[j].tag == 4 && tlvs.items[j].len == 6)
          fb_mac_to_str(tlvs.items[j].value, addr);
      }
      fb_tlvs_free(&tlvs);
      if (addr[0]) {
        dev = find_device(out, addr);
        if (!dev) {
          out->items =
              realloc(out->items, (out->count + 1) * sizeof(fb_device));
          memset(&out->items[out->count], 0, sizeof(fb_device));
          dev = &out->items[out->count];
          out->count++;
        }
        parse_bonded_device(fr->data, fr->data_len, dev);
      }
    } else if (fr->cmd == 0x36) {
      fb_device tmp;
      char addr[24];
      int type;
      memset(&tmp, 0, sizeof(tmp));
      parse_device_report(fr->data, fr->data_len, &tmp, addr, sizeof(addr),
                          &type);
      if (addr[0]) {
        fb_device *dev = find_device(out, addr);
        if (dev) {
          if (tmp.has_conn) {
            dev->conn_state = tmp.conn_state;
            dev->business_state = tmp.business_state;
            dev->in_business = tmp.in_business;
          }
          if (tmp.has_back_conn)
            dev->back_conn_permit = tmp.back_conn_permit;
          if (tmp.has_aas)
            dev->allow_audio_auto_switch = tmp.allow_audio_auto_switch;
          if (tmp.has_lock)
            dev->lock_channel = tmp.lock_channel;
        }
      }
    }
  }
  sort_devices_by_index(out);
  fb_frames_free(frames);
  return 1;
}

void fb_devices_free(fb_devices *devs) {
  if (devs->items)
    free(devs->items);
  devs->items = NULL;
  devs->count = 0;
}

int fb_ctrl_single_device_setting(fb_ctrl *c, fb_setres *out, int sub,
                                  const char *mac) {
  fb_frames *frames;
  uint8_t macb[6];
  uint8_t *payload;
  size_t payload_len;
  size_t i;
  int found = 0;

  memset(out, 0, sizeof(*out));
  if (!fb_valid_mac(mac))
    return 0;
  fb_mac_to_bytes(mac, macb);
  payload = fb_cmd_single_device_setting(sub, macb, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  if (!frames)
    return 0;

  for (i = 0; i < frames->count; i++) {
    fb_frame *fr = &frames->items[i];
    if (fr->svc == 0x2B && fr->cmd == 0x33) {
      fb_tlvs tlvs = fb_parse_tlv(fr->data, fr->data_len);
      size_t j;
      int has = 0;
      for (j = 0; j < tlvs.count; j++) {
        fb_tlv *t = &tlvs.items[j];
        if (t->tag == 30 && t->len == 1) {
          out->result_code = t->value[0];
          out->has_result_code = 1;
          has = 1;
        } else if (t->tag == 31 && t->len == 1) {
          out->success = t->value[0];
          out->has_success = 1;
          snprintf(out->result_name, sizeof(out->result_name), "%d",
                   t->value[0]);
          has = 1;
        }
      }
      fb_tlvs_free(&tlvs);
      if (has)
        found = 1;
      break;
    }
  }

  if (!found &&
      is_status_response(frames->items[0].data, frames->items[0].data_len)) {
    out->has_status = 1;
    out->status =
        parse_status_code(frames->items[0].data, frames->items[0].data_len);
    out->has_success = 1;
    out->success = (out->status == 0 || out->status == FB_STATUS_OK);
    found = 1;
  }

  fb_frames_free(frames);
  return found;
}

int fb_ctrl_set_primary_device(fb_ctrl *c, fb_setres *out, const char *mac) {
  fb_frames *frames;
  const fb_frame *f;
  uint8_t macb[6];
  uint8_t *payload;
  size_t payload_len;

  memset(out, 0, sizeof(*out));
  if (!fb_valid_mac(mac))
    return 0;
  fb_mac_to_bytes(mac, macb);
  payload = fb_cmd_set_primary_device(macb, &payload_len);
  frames = fb_ctrl_send(c, payload, payload_len, 2.0);
  free(payload);
  if (!frames)
    return 0;

  f = match_frame(frames, 0x2B, 0x32);
  if (f) {
    out->success = 1;
    out->has_success = 1;
    set_raw_hex(out->raw_hex, sizeof(out->raw_hex), f->data, f->data_len);
  } else {
    out->has_success = 0;
    set_raw_hex(out->raw_hex, sizeof(out->raw_hex), frames->items[0].data,
                frames->items[0].data_len);
  }
  fb_frames_free(frames);
  return 1;
}

int fb_ctrl_get_cloud_version(fb_ctrl *c, char *out_hex, size_t outsz) {
  fb_frames *frames;
  const fb_frame *f;
  int rc = 0;

  frames =
      fb_ctrl_send(c, FB_CMD_CLOUD_VERSION, sizeof(FB_CMD_CLOUD_VERSION), 2.0);
  f = match_frame(frames, 0x09, 0x08);
  if (f) {
    set_raw_hex(out_hex, outsz, f->data, f->data_len);
    rc = 1;
  }
  fb_frames_free(frames);
  return rc;
}

int fb_ctrl_get_ota_params(fb_ctrl *c, char *out_hex, size_t outsz) {
  fb_frames *frames;
  const fb_frame *f;
  int rc = 0;

  frames = fb_ctrl_send(c, FB_CMD_GET_OTA_PARAMS, sizeof(FB_CMD_GET_OTA_PARAMS),
                        2.0);
  f = match_frame(frames, 0x09, 0x02);
  if (f) {
    set_raw_hex(out_hex, outsz, f->data, f->data_len);
    rc = 1;
  }
  fb_frames_free(frames);
  return rc;
}
