/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef FB_PROTOCOL_H
#define FB_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

typedef struct
{
    uint8_t *data;
    size_t len;
    size_t cap;
} fb_buf;

void fb_buf_init(fb_buf *b);
void fb_buf_put(fb_buf *b, uint8_t v);
void fb_buf_append(fb_buf *b, const uint8_t *p, size_t n);
uint8_t *fb_buf_take(fb_buf *b, size_t *len);
void fb_buf_free(fb_buf *b);

extern const uint8_t FB_CMD_BATTERY[8];
extern const size_t FB_CMD_BATTERY_LEN;
extern const uint8_t FB_CMD_VERSION[];
extern const size_t FB_CMD_VERSION_LEN;
extern const uint8_t FB_CMD_CMD_01_1D[5];
extern const uint8_t FB_CMD_GET_SERVICE_ABILITY[4];
extern const uint8_t FB_CMD_GET_COMMAND_ABILITY[4];
extern const uint8_t FB_CMD_GET_DOUBLE_CLICK[4];
extern const uint8_t FB_CMD_CLOUD_VERSION[2];
extern const uint8_t FB_CMD_GET_OTA_PARAMS[4];
extern const uint8_t FB_CMD_CANCEL_OTA[2];
extern const uint8_t FB_CMD_CHECK_OTA_STATE[4];
extern const uint8_t FB_CMD_LANGUAGE_PSI[5];
extern const uint8_t FB_CMD_GET_LANGUAGE[8];
extern const uint8_t FB_CMD_GET_GREET[4];
extern const uint8_t FB_CMD_GET_WEAR[4];
extern const uint8_t FB_CMD_GET_LONG_PRESS[8];
extern const uint8_t FB_CMD_GET_SHORT_PRESS[8];
extern const uint8_t FB_CMD_GET_SLIDE[8];
extern const uint8_t FB_CMD_GET_SAVING_MODE[4];
extern const uint8_t FB_CMD_GET_INTELLECT_VOLUME[4];
extern const uint8_t FB_CMD_GET_ANC_STATE[4];
extern const uint8_t FB_CMD_GET_ANC_MODE_LEVEL[4];
extern const uint8_t FB_CMD_QUERY_NOISE_REDUCTION_MODE[4];
extern const uint8_t FB_CMD_GET_NOISE_CONTROL[6];
extern const uint8_t FB_CMD_GET_EQ[4];
extern const uint8_t FB_CMD_GET_EQ_EXTENDED_SUPPORT[4];
extern const uint8_t FB_CMD_GET_TRIPLE_CLICK[6];
extern const uint8_t FB_CMD_GET_DOUBLE_CLICK_MBB[6];
extern const uint8_t FB_CMD_GET_DOUBLE_CLICK_CALL[4];
extern const uint8_t FB_CMD_GET_LONG_PRESS_MBB[6];
extern const uint8_t FB_CMD_GET_LONG_PRESS_CALL[6];
extern const uint8_t FB_CMD_GET_SLIDE_MBB[6];
extern const uint8_t FB_CMD_GET_PINCH[6];
extern const uint8_t FB_CMD_GET_LIGHT_HOLD[6];
extern const uint8_t FB_CMD_GET_GAME_LOW_LATENCY[4];
extern const uint8_t FB_CMD_GET_DUAL_CONNECT[4];
extern const uint8_t FB_CMD_GET_TRANSLATE_MODE[4];
extern const uint8_t FB_CMD_GET_VOICE_ENHANCE[4];
extern const uint8_t FB_CMD_GET_32K_HD[4];
extern const uint8_t FB_CMD_GET_HD_SWITCH[5];
extern const uint8_t FB_CMD_GET_LEFT_RIGHT_EAR[4];
extern const uint8_t FB_CMD_GET_WIND_MODE[4];
extern const uint8_t FB_CMD_GET_WEARING_STATUS[6];
extern const uint8_t FB_CMD_GET_DORMANT_TIME[4];
extern const uint8_t FB_CMD_GET_SILENT_UPGRADE[4];
extern const uint8_t FB_CMD_GET_BT_MAIN_STATUS[4];
extern const uint8_t FB_CMD_GET_CLOSE_COVER_REMIND[4];
extern const uint8_t FB_CMD_GET_MUSIC_MODE[4];
extern const uint8_t FB_CMD_GET_HEALTH_ALERTS[4];
extern const uint8_t FB_CMD_FACTORY_RESET[5];
extern const uint8_t FB_CMD_GET_AMBIENT_SOUND[4];
extern const uint8_t FB_CMD_GET_CONNECT_ABILITY[4];
extern const uint8_t FB_CMD_QUERY_PAIR[4];
extern const uint8_t FB_CMD_STATE_PAIR[5];
extern const uint8_t FB_CMD_GET_DEVICES_BONDED[4];
extern const uint8_t FB_CMD_GET_FIT_CHECK[4];
extern const uint8_t FB_CMD_EXIT_FIT_CHECK[4];
extern const uint8_t FB_CMD_GET_FIT_DETECT_VERSION[4];
extern const uint8_t FB_CMD_HEARTBEAT[4];

uint8_t *fb_cmd_set_double_click_mbb(int left, int right, size_t *len);
uint8_t *fb_cmd_set_long_press_mbb(int left, int right, size_t *len);
uint8_t *fb_cmd_set_slide_mbb(int left, int right, size_t *len);
uint8_t *fb_cmd_set_pinch(int left, int right, size_t *len);
uint8_t *fb_cmd_set_triple_click(int left, int right, size_t *len);
uint8_t *fb_cmd_set_light_hold(int left, int right, size_t *len);
uint8_t *fb_cmd_set_greet(int enable, size_t *len);
uint8_t *fb_cmd_set_wear(int enable, size_t *len);
uint8_t *fb_cmd_set_saving_mode(int enable, size_t *len);
uint8_t *fb_cmd_set_intellect_volume(int enable, size_t *len);
uint8_t *fb_cmd_set_game_low_latency(int enable, size_t *len);
uint8_t *fb_cmd_set_dual_connect(int enable, size_t *len);
uint8_t *fb_cmd_set_translate_mode(int enable, size_t *len);
uint8_t *fb_cmd_set_voice_enhance(int enable, size_t *len);
uint8_t *fb_cmd_set_32k_hd(int enable, size_t *len);
uint8_t *fb_cmd_set_hd_switch(int enable, size_t *len);
uint8_t *fb_cmd_set_left_right_ear(int enable, size_t *len);
uint8_t *fb_cmd_set_wind_mode(int enable, size_t *len);
uint8_t *fb_cmd_set_silent_upgrade(int enable, size_t *len);
uint8_t *fb_cmd_set_health_alerts(int enable, size_t *len);
uint8_t *fb_cmd_set_language(const char *lang, size_t *len);
uint8_t *fb_cmd_set_anc_state(int mode, size_t *len);
uint8_t *fb_cmd_set_anc_state_level(int mode, int level, size_t *len);
uint8_t *fb_cmd_set_anc_level(int level, size_t *len);
uint8_t *fb_cmd_set_noise_control(int mode, int value, size_t *len);
uint8_t *fb_cmd_set_eq(int mode, size_t *len);
uint8_t *fb_cmd_set_dormant_time(int option, int seconds, size_t *len);
uint8_t *fb_cmd_get_bonded_by_index(int index, size_t *len);
uint8_t *fb_cmd_get_bonded_by_mac(const uint8_t *mac, size_t *len);
uint8_t *fb_cmd_set_primary_device(const uint8_t *mac, size_t *len);
uint8_t *fb_cmd_single_device_setting(int sub, const uint8_t *mac, size_t *len);

void fb_mac_to_bytes(const char *mac, uint8_t out[6]);
void fb_mac_to_str(const uint8_t *raw, char *out);
int fb_valid_mac(const char *mac);

typedef struct
{
    const char *key;
    const char *alias;
} fb_strpair;

typedef struct
{
    const char *name;
    int value;
} fb_ival;

/* gesture/action tables */
extern const char *const FB_NC_MODES[3];
extern const char *const FB_NC_LEVELS[4];
extern const char *const FB_EQ_MODES[4];

extern const fb_ival FB_NC_MODE_ALIASES[];
extern const fb_ival FB_NC_LEVEL_ALIASES[];
extern const fb_ival FB_EQ_MODE_ALIASES[];
extern const fb_strpair FB_GESTURE_ALIASES[];

int fb_alias_value(const fb_ival *table, const char *name, int *out);
int fb_resolve_anc_level(const char *s, int *out);
int fb_resolve_eq_mode(const char *s, int *out);
int fb_gesture_from_alias(const char *alias);

typedef struct
{
    const char *key;
    const char *name;
    const uint8_t *get;
    size_t get_len;
    const uint8_t *set_prefix;
    size_t set_prefix_len;
    int svc;
    int cmd;
    int set_cmd;
    int nc_action;
} fb_gesture;

extern const fb_gesture FB_GESTURES[6];
extern const size_t FB_GESTURE_COUNT;

const char *fb_gesture_name(int g);
const char *fb_gesture_lp_name(void);
int fb_gesture_nc_action(int g);

typedef struct
{
    const char *key;
    const char *name;
    const char *get_name_label;
    const uint8_t *get;
    size_t get_len;
    const uint8_t *set;
    size_t set_len;
    int svc;
    int cmd;
    int set_cmd;
} fb_feature;

extern const fb_feature FB_FEATURABLE[14];
extern const size_t FB_FEATURABLE_COUNT;

#endif