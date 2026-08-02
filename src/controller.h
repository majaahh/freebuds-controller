/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef FB_CONTROLLER_H
#define FB_CONTROLLER_H

#include <stddef.h>
#include <stdint.h>

#include "frame.h"
#include "protocol.h"

#define FB_STATUS_OK 100000u
#define FB_STATUS_NOT_SUPPORTED 100003u

typedef struct {
  int left_battery;
  int right_battery;
  int box_battery;
} fb_battery;

typedef struct {
  char model[100];
  char firmware[100];
  char serial[100];
  char bt_version[100];
  char bt_prefix[100];
  char bud_serials[100];
  int has_model, has_firmware, has_serial, has_bt_version, has_bt_prefix,
      has_bud_serials;
  char other[8][100];
  int other_tags[8];
  size_t other_count;
} fb_version;

typedef struct {
  int enabled;
  int has_enabled;
  uint32_t status;
  int has_status;
  int status_ok;
  char raw_hex[600];
} fb_boolres;

typedef struct {
  uint32_t value;
  int has_value;
  uint32_t status;
  int has_status;
  int status_ok;
  char raw_hex[600];
} fb_uintres;

typedef struct {
  int left, right;
  int has_left, has_right;
  char left_name[64], right_name[64];
  int supported[32];
  size_t supported_count;
  char supported_names[32][64];
  int call_left, call_right;
  int has_call_left, has_call_right;
  uint32_t status;
  int has_status;
  int status_ok;
  char raw_hex[600];
} fb_touchres;

typedef struct {
  int success;
  int has_success;
  uint32_t status;
  int has_status;
  int result_code;
  int has_result_code;
  char result_name[64];
  char raw_hex[600];
} fb_setres;

typedef struct {
  int mode;
  int has_mode;
  int level;
  int has_level;
  int common_index;
  int has_common_index;
  int plane_index;
  int has_plane_index;
  int fly_mode;
  int has_fly_mode;
  int mode_scene;
  int has_mode_scene;
  int mode_voice;
  int has_mode_voice;
  int mode_noise;
  int has_mode_noise;
  int extra;
  int has_extra;
  uint32_t status;
  int has_status;
  int status_ok;
  char source[24];
  char raw_hex[600];
} fb_ancres;

typedef struct {
  int support;
  int has_support;
  int mode;
  int has_mode;
  int recommended;
  int has_recommended;
  int modes[16];
  size_t mode_count;
  char custom_hex[600];
  uint32_t status;
  int has_status;
  int status_ok;
  char raw_hex[600];
} fb_eqres;

typedef struct {
  char current[128];
  char tag3[512];
  int unit;
  int has_unit;
  char other[8][128];
  int other_tags[8];
  size_t other_count;
} fb_langres;

typedef struct {
  int left_ear, right_ear;
  int has_left_ear, has_right_ear;
  int left_in, right_in;
  uint32_t status;
  int has_status;
  int status_ok;
  char raw_hex[600];
} fb_wearres;

typedef struct {
  int number;
  int has_number;
  int index;
  int has_index;
  char addr[24];
  int conn_state;
  int business_state;
  int in_business;
  int has_conn;
  int type;
  int has_type;
  int primary;
  int has_primary;
  int back_conn_permit;
  int has_back_conn;
  char name[64];
  int allow_audio_auto_switch;
  int has_aas;
  int nearlink;
  int has_nearlink;
  int lock_channel;
  int has_lock;
} fb_device;

typedef struct {
  fb_device *items;
  size_t count;
} fb_devices;

typedef struct {
  char mac[24];
  int sock;
  int connected;
} fb_ctrl;

int fb_ctrl_connect(fb_ctrl *c, const char *mac, int channel);
void fb_ctrl_disconnect(fb_ctrl *c);
fb_frames *fb_ctrl_send(fb_ctrl *c, const uint8_t *cmd, size_t cmd_len,
                        double timeout);

void fb_hexdump(const uint8_t *data, size_t len, char *out, size_t outsz);

int fb_ctrl_get_battery(fb_ctrl *c, fb_battery *out);
int fb_ctrl_get_version(fb_ctrl *c, fb_version *out);
int fb_ctrl_get_bool(fb_ctrl *c, fb_boolres *out, const uint8_t *get_cmd,
                     size_t get_len, int svc, int get_cmd_id, int set_cmd_id);
int fb_ctrl_set_bool(fb_ctrl *c, fb_setres *out, const uint8_t *set_cmd,
                     size_t set_len, int svc, int set_cmd_id);
int fb_ctrl_get_uint(fb_ctrl *c, fb_uintres *out, const uint8_t *cmd,
                     size_t len, int svc, int cmd_id);
int fb_ctrl_get_touch(fb_ctrl *c, fb_touchres *out, const fb_gesture *g);
int fb_ctrl_set_touch(fb_ctrl *c, fb_setres *out, const fb_gesture *g, int side,
                      int action);
int fb_ctrl_set_anc_state(fb_ctrl *c, fb_setres *out, int mode);
int fb_ctrl_set_anc_state_extended(fb_ctrl *c, fb_setres *out, int mode,
                                   int level);
int fb_ctrl_set_anc_level(fb_ctrl *c, fb_setres *out, int level);
int fb_ctrl_set_noise_control(fb_ctrl *c, fb_setres *out, int mode, int value);
int fb_ctrl_set_noise_mode(fb_ctrl *c, fb_setres *out, int mode);
int fb_ctrl_get_anc_state(fb_ctrl *c, fb_ancres *out);
int fb_ctrl_get_anc_mode_level(fb_ctrl *c, fb_ancres *out);
int fb_ctrl_query_nr_mode(fb_ctrl *c, fb_ancres *out);
int fb_ctrl_get_noise_control_lr(fb_ctrl *c, fb_ancres *out);
int fb_ctrl_get_sound_effect(fb_ctrl *c, fb_eqres *out);
int fb_ctrl_set_sound_effect(fb_ctrl *c, fb_setres *out, int mode);
int fb_ctrl_get_language(fb_ctrl *c, fb_langres *out);
int fb_ctrl_set_language(fb_ctrl *c, fb_setres *out, const char *lang);
int fb_ctrl_get_wearing_status(fb_ctrl *c, fb_wearres *out);
int fb_ctrl_set_dormant_time(fb_ctrl *c, fb_setres *out, int option,
                             int seconds);
int fb_ctrl_start_pair(fb_ctrl *c, fb_setres *out);
int fb_ctrl_exit_fit_check(fb_ctrl *c, fb_setres *out);
int fb_ctrl_get_bonded_devices(fb_ctrl *c, fb_devices *out);
int fb_ctrl_single_device_setting(fb_ctrl *c, fb_setres *out, int sub,
                                  const char *mac);
int fb_ctrl_set_primary_device(fb_ctrl *c, fb_setres *out, const char *mac);
int fb_ctrl_get_cloud_version(fb_ctrl *c, char *out_hex, size_t outsz);
int fb_ctrl_get_ota_params(fb_ctrl *c, char *out_hex, size_t outsz);
void fb_devices_free(fb_devices *devs);

#endif