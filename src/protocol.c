/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#include "protocol.h"

void fb_buf_init(fb_buf *b)
{
    b->data = NULL;
    b->len = 0;
    b->cap = 0;
}

void fb_buf_put(fb_buf *b, uint8_t v)
{
    if (b->len == b->cap)
    {
        size_t ncap = b->cap ? b->cap * 2 : 16;
        uint8_t *nd = realloc(b->data, ncap);
        if (!nd)
            return;
        b->data = nd;
        b->cap = ncap;
    }
    b->data[b->len++] = v;
}

void fb_buf_append(fb_buf *b, const uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++)
        fb_buf_put(b, p[i]);
}

uint8_t *fb_buf_take(fb_buf *b, size_t *len)
{
    uint8_t *d = b->data;
    if (len)
        *len = b->len;
    b->data = NULL;
    b->len = 0;
    b->cap = 0;
    return d;
}

void fb_buf_free(fb_buf *b)
{
    free(b->data);
    b->data = NULL;
    b->len = 0;
    b->cap = 0;
}

const uint8_t FB_CMD_BATTERY[8] = {0x01, 0x08, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00};
const size_t FB_CMD_BATTERY_LEN = 8;

const uint8_t FB_CMD_VERSION[] = {
    0x01, 0x07, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00, 0x04, 0x00, 0x05, 0x00,
    0x06, 0x00, 0x07, 0x00, 0x08, 0x00, 0x09, 0x00, 0x0A, 0x00, 0x0B, 0x00, 0x0C, 0x00,
};
const size_t FB_CMD_VERSION_LEN = 26;

const uint8_t FB_CMD_CMD_01_1D[5] = {0x01, 0x1D, 0x01, 0x01, 0x01};
const uint8_t FB_CMD_GET_SERVICE_ABILITY[4] = {0x01, 0x02, 0x01, 0x00};
const uint8_t FB_CMD_GET_COMMAND_ABILITY[4] = {0x01, 0x03, 0x01, 0x00};
const uint8_t FB_CMD_GET_DOUBLE_CLICK[4] = {0x01, 0x20, 0x03, 0x00};
const uint8_t FB_CMD_CLOUD_VERSION[2] = {0x09, 0x08};
const uint8_t FB_CMD_GET_OTA_PARAMS[4] = {0x09, 0x02, 0x01, 0x00};
const uint8_t FB_CMD_CANCEL_OTA[2] = {0x09, 0x08};
const uint8_t FB_CMD_CHECK_OTA_STATE[4] = {0x09, 0x01, 0x01, 0x00};
const uint8_t FB_CMD_LANGUAGE_PSI[5] = {0x0A, 0x0E, 0x02, 0x01, 0x00};
const uint8_t FB_CMD_GET_LANGUAGE[8] = {0x0C, 0x02, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00};
const uint8_t FB_CMD_GET_GREET[4] = {0x2B, 0x0F, 0x01, 0x00};
const uint8_t FB_CMD_GET_WEAR[4] = {0x2B, 0x11, 0x01, 0x00};
const uint8_t FB_CMD_GET_LONG_PRESS[8] = {0x2B, 0x17, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00};
const uint8_t FB_CMD_GET_SHORT_PRESS[8] = {0x2B, 0x21, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00};
const uint8_t FB_CMD_GET_SLIDE[8] = {0x2B, 0x1F, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00};
const uint8_t FB_CMD_GET_SAVING_MODE[4] = {0x2B, 0x1D, 0x01, 0x00};
const uint8_t FB_CMD_GET_INTELLECT_VOLUME[4] = {0x2B, 0x23, 0x01, 0x00};
const uint8_t FB_CMD_GET_ANC_STATE[4] = {0x2B, 0x05, 0x01, 0x00};
const uint8_t FB_CMD_GET_ANC_MODE_LEVEL[4] = {0x2B, 0x07, 0x01, 0x00};
const uint8_t FB_CMD_QUERY_NOISE_REDUCTION_MODE[4] = {0x2B, 0x2A, 0x01, 0x00};
const uint8_t FB_CMD_GET_NOISE_CONTROL[6] = {0x2B, 0x19, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_EQ[4] = {0x2B, 0x4A, 0x02, 0x00};
const uint8_t FB_CMD_GET_EQ_EXTENDED_SUPPORT[4] = {0x2B, 0xA8, 0x01, 0x01};
const uint8_t FB_CMD_GET_TRIPLE_CLICK[6] = {0x01, 0x26, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_DOUBLE_CLICK_MBB[6] = {0x01, 0x20, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_DOUBLE_CLICK_CALL[4] = {0x01, 0x20, 0x04, 0x00};
const uint8_t FB_CMD_GET_LONG_PRESS_MBB[6] = {0x2B, 0x17, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_LONG_PRESS_CALL[6] = {0x2B, 0x17, 0x04, 0x00, 0x05, 0x00};
const uint8_t FB_CMD_GET_SLIDE_MBB[6] = {0x2B, 0x1F, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_PINCH[6] = {0x2B, 0x21, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_LIGHT_HOLD[6] = {0x2B, 0x93, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_GAME_LOW_LATENCY[4] = {0x2B, 0x6C, 0x02, 0x00};
const uint8_t FB_CMD_GET_DUAL_CONNECT[4] = {0x2B, 0x2F, 0x01, 0x00};
const uint8_t FB_CMD_GET_TRANSLATE_MODE[4] = {0x2B, 0x4D, 0x01, 0x00};
const uint8_t FB_CMD_GET_VOICE_ENHANCE[4] = {0x2B, 0x42, 0x01, 0x01};
const uint8_t FB_CMD_GET_32K_HD[4] = {0x2B, 0x46, 0x01, 0x01};
const uint8_t FB_CMD_GET_HD_SWITCH[5] = {0x2B, 0x5E, 0x01, 0x01, 0x01};
const uint8_t FB_CMD_GET_LEFT_RIGHT_EAR[4] = {0x2B, 0x9A, 0x01, 0x00};
const uint8_t FB_CMD_GET_WIND_MODE[4] = {0x2B, 0x95, 0x01, 0x01};
const uint8_t FB_CMD_GET_WEARING_STATUS[6] = {0x2B, 0x25, 0x01, 0x00, 0x02, 0x00};
const uint8_t FB_CMD_GET_DORMANT_TIME[4] = {0x2B, 0x48, 0x01, 0x00};
const uint8_t FB_CMD_GET_SILENT_UPGRADE[4] = {0x2B, 0x70, 0x01, 0x01};
const uint8_t FB_CMD_GET_BT_MAIN_STATUS[4] = {0x2B, 0x6A, 0x01, 0x01};
const uint8_t FB_CMD_GET_CLOSE_COVER_REMIND[4] = {0x2B, 0x7F, 0x01, 0x01};
const uint8_t FB_CMD_GET_MUSIC_MODE[4] = {0x2B, 0x53, 0x02, 0x00};
const uint8_t FB_CMD_GET_HEALTH_ALERTS[4] = {0x2B, 0x61, 0x01, 0x00};
const uint8_t FB_CMD_FACTORY_RESET[5] = {0x01, 0x0D, 0x01, 0x01, 0x01};
const uint8_t FB_CMD_GET_AMBIENT_SOUND[4] = {0x2B, 0x2C, 0x01, 0x00};
const uint8_t FB_CMD_GET_CONNECT_ABILITY[4] = {0x2B, 0x2D, 0x01, 0x00};
const uint8_t FB_CMD_QUERY_PAIR[4] = {0x2B, 0x8F, 0x01, 0x00};
const uint8_t FB_CMD_STATE_PAIR[5] = {0x2B, 0x90, 0x01, 0x01, 0x01};
const uint8_t FB_CMD_GET_DEVICES_BONDED[4] = {0x2B, 0x31, 0x01, 0x00};
const uint8_t FB_CMD_GET_FIT_CHECK[4] = {0x2B, 0x26, 0x01, 0x00};
const uint8_t FB_CMD_EXIT_FIT_CHECK[4] = {0x2B, 0x26, 0x03, 0x00};
const uint8_t FB_CMD_GET_FIT_DETECT_VERSION[4] = {0x2B, 0x37, 0x01, 0x00};
const uint8_t FB_CMD_HEARTBEAT[4] = {0x2B, 0x4E, 0x01, 0x00};

static uint8_t *build_side_pair(uint8_t svc, uint8_t cmd, int left, int right, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, svc);
    fb_buf_put(&b, cmd);
    if (left >= 0)
    {
        fb_buf_put(&b, 0x01);
        fb_buf_put(&b, 0x01);
        fb_buf_put(&b, (uint8_t)(left & 0xFF));
    }
    if (right >= 0)
    {
        fb_buf_put(&b, 0x02);
        fb_buf_put(&b, 0x01);
        fb_buf_put(&b, (uint8_t)(right & 0xFF));
    }
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_double_click_mbb(int left, int right, size_t *len)
{
    return build_side_pair(0x01, 0x1F, left, right, len);
}

uint8_t *fb_cmd_set_long_press_mbb(int left, int right, size_t *len)
{
    return build_side_pair(0x2B, 0x16, left, right, len);
}

uint8_t *fb_cmd_set_slide_mbb(int left, int right, size_t *len)
{
    return build_side_pair(0x2B, 0x1E, left, right, len);
}

uint8_t *fb_cmd_set_pinch(int left, int right, size_t *len)
{
    return build_side_pair(0x2B, 0x20, left, right, len);
}

uint8_t *fb_cmd_set_triple_click(int left, int right, size_t *len)
{
    return build_side_pair(0x01, 0x25, left, right, len);
}

uint8_t *fb_cmd_set_light_hold(int left, int right, size_t *len)
{
    return build_side_pair(0x2B, 0x92, left, right, len);
}

static uint8_t *build_bool_set(uint8_t svc, uint8_t cmd, int enable, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, svc);
    fb_buf_put(&b, cmd);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, enable ? 0x01 : 0x00);
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_greet(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x0E, enable, len);
}

uint8_t *fb_cmd_set_wear(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x10, enable, len);
}

uint8_t *fb_cmd_set_saving_mode(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x1C, enable, len);
}

uint8_t *fb_cmd_set_intellect_volume(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x22, enable, len);
}

uint8_t *fb_cmd_set_game_low_latency(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x6C, enable, len);
}

uint8_t *fb_cmd_set_dual_connect(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x2E, enable, len);
}

uint8_t *fb_cmd_set_translate_mode(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x4C, enable, len);
}

uint8_t *fb_cmd_set_voice_enhance(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x41, enable, len);
}

uint8_t *fb_cmd_set_32k_hd(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x45, enable, len);
}

uint8_t *fb_cmd_set_hd_switch(int enable, size_t *len)
{
    fb_buf b;
    uint8_t v = enable ? 0x01 : 0x00;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x5D);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x02);
    fb_buf_put(&b, v);
    fb_buf_put(&b, v);
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_left_right_ear(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x99, enable, len);
}

uint8_t *fb_cmd_set_wind_mode(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x94, enable, len);
}

uint8_t *fb_cmd_set_silent_upgrade(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x6F, enable, len);
}

uint8_t *fb_cmd_set_health_alerts(int enable, size_t *len)
{
    return build_bool_set(0x2B, 0x60, enable, len);
}

uint8_t *fb_cmd_set_language(const char *lang, size_t *len)
{
    fb_buf b;
    size_t n = strlen(lang);
    fb_buf_init(&b);
    fb_buf_put(&b, 0x0C);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)n);
    fb_buf_append(&b, (const uint8_t *)lang, n);
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_anc_state(int mode, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x04);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(mode & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_anc_state_level(int mode, int level, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x04);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x02);
    fb_buf_put(&b, (uint8_t)(mode & 0xFF));
    fb_buf_put(&b, (uint8_t)(level & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_anc_level(int level, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x08);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(level & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_noise_control(int mode, int value, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x18);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(mode & 0xFF));
    if (value >= 0)
    {
        fb_buf_put(&b, 0x02);
        fb_buf_put(&b, 0x01);
        fb_buf_put(&b, (uint8_t)(value & 0xFF));
    }
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_eq(int mode, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x49);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(mode & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_dormant_time(int option, int seconds, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x47);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(option & 0xFF));
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x04);
    fb_buf_put(&b, (uint8_t)((seconds >> 24) & 0xFF));
    fb_buf_put(&b, (uint8_t)((seconds >> 16) & 0xFF));
    fb_buf_put(&b, (uint8_t)((seconds >> 8) & 0xFF));
    fb_buf_put(&b, (uint8_t)(seconds & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_get_bonded_by_index(int index, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x31);
    fb_buf_put(&b, 0x03);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, (uint8_t)(index & 0xFF));
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_get_bonded_by_mac(const uint8_t *mac, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x31);
    fb_buf_put(&b, 0x04);
    fb_buf_put(&b, 0x06);
    fb_buf_append(&b, mac, 6);
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_set_primary_device(const uint8_t *mac, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x32);
    fb_buf_put(&b, 0x01);
    fb_buf_put(&b, 0x06);
    fb_buf_append(&b, mac, 6);
    return fb_buf_take(&b, len);
}

uint8_t *fb_cmd_single_device_setting(int sub, const uint8_t *mac, size_t *len)
{
    fb_buf b;
    fb_buf_init(&b);
    fb_buf_put(&b, 0x2B);
    fb_buf_put(&b, 0x33);
    fb_buf_put(&b, (uint8_t)(sub & 0xFF));
    fb_buf_put(&b, 0x06);
    fb_buf_append(&b, mac, 6);
    return fb_buf_take(&b, len);
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

void fb_mac_to_bytes(const char *mac, uint8_t out[6])
{
    int i, hi, lo;
    for (i = 0; i < 6; i++)
    {
        hi = hexval(mac[i * 3]);
        lo = hexval(mac[i * 3 + 1]);
        out[i] = (uint8_t)((hi << 4) | lo);
    }
}

void fb_mac_to_str(const uint8_t *raw, char *out)
{
    static const char *HEX = "0123456789ABCDEF";
    int i;
    for (i = 0; i < 6; i++)
    {
        if (i)
            *out++ = ':';
        *out++ = HEX[raw[i] >> 4];
        *out++ = HEX[raw[i] & 0xF];
    }
    *out = '\0';
}

int fb_valid_mac(const char *mac)
{
    size_t len = strlen(mac);
    size_t i;
    if (len != 17)
        return 0;
    for (i = 0; i < 17; i++)
    {
        if (i % 3 == 2)
        {
            if (mac[i] != ':')
                return 0;
        }
        else if (hexval(mac[i]) < 0)
            return 0;
    }
    return 1;
}

const char *const FB_NC_MODES[3] = {"Off", "On", "Awareness"};

const char *const FB_NC_LEVELS[4] = {"General", "Cozy", "Ultra", "Dynamic"};

const char *const FB_EQ_MODES[4] = {"Default", "Bass boost", "Treble boost", "Voices"};

const fb_ival FB_NC_MODE_ALIASES[] = {
    {"off", 0},
    {"0", 0},
    {"cancel", 0},
    {"on", 1},
    {"noise", 1},
    {"1", 1},
    {"aware", 2},
    {"awareness", 2},
    {"transparent", 2},
    {"pass", 2},
    {"pass_through", 2},
    {"2", 2},
    {NULL, 0},
};

const fb_ival FB_NC_LEVEL_ALIASES[] = {
    {"general", 0},
    {"balance", 0},
    {"0", 0},
    {"cozy", 1},
    {"comfortable", 1},
    {"light", 1},
    {"1", 1},
    {"ultra", 2},
    {"deep", 2},
    {"deeply", 2},
    {"depth", 2},
    {"2", 2},
    {"dynamic", 3},
    {"ai", 3},
    {"smart", 3},
    {"3", 3},
    {NULL, 0},
};

const fb_ival FB_EQ_MODE_ALIASES[] = {
    {"default", 1},
    {"balanced", 1},
    {"1", 1},
    {"bass", 2},
    {"bassboost", 2},
    {"2", 2},
    {"treble", 3},
    {"trebleboost", 3},
    {"3", 3},
    {"voices", 9},
    {"voice", 9},
    {"clearvoice", 9},
    {"9", 9},
    {NULL, 0},
};

const fb_strpair FB_GESTURE_ALIASES[] = {
    {"long_press", "lp"},
    {"long_press", "long"},
    {"pinch", "sp"},
    {"slide", "sl"},
    {"double_click", "dc"},
    {"double_click", "double"},
    {"triple_click", "triple"},
    {"triple_click", "tri"},
    {"triple_click", "tc"},
    {"light_hold", "lhold"},
    {"light_hold", "lh"},
    {NULL, NULL},
};

int fb_alias_value(const fb_ival *table, const char *name, int *out)
{
    int i;
    for (i = 0; table[i].name; i++)
    {
        if (strcmp(table[i].name, name) == 0)
        {
            *out = table[i].value;
            return 1;
        }
    }
    return 0;
}

static int resolve_alias(const fb_ival *table, const char *s, int *out)
{
    int i;
    char buf[64];
    size_t n = strlen(s);
    if (n == 0 || n >= sizeof(buf))
        return 0;
    for (i = 0; (size_t)i < n; i++)
        buf[i] = (char)tolower((unsigned char)s[i]);
    buf[n] = '\0';
    return fb_alias_value(table, buf, out);
}

int fb_resolve_anc_level(const char *s, int *out)
{
    return resolve_alias(FB_NC_LEVEL_ALIASES, s, out);
}

int fb_resolve_eq_mode(const char *s, int *out)
{
    return resolve_alias(FB_EQ_MODE_ALIASES, s, out);
}

const fb_gesture FB_GESTURES[6] = {
    {
        "long_press",
        "Long press",
        FB_CMD_GET_LONG_PRESS_MBB,
        sizeof(FB_CMD_GET_LONG_PRESS_MBB),
        NULL,
        0,
        0x2B,
        0x17,
        0x16,
        10,
    },
    {
        "pinch",
        "Pinch",
        FB_CMD_GET_PINCH,
        sizeof(FB_CMD_GET_PINCH),
        NULL,
        0,
        0x2B,
        0x21,
        0x20,
        -1,
    },
    {
        "slide",
        "Slide",
        FB_CMD_GET_SLIDE_MBB,
        sizeof(FB_CMD_GET_SLIDE_MBB),
        NULL,
        0,
        0x2B,
        0x1F,
        0x1E,
        -1,
    },
    {
        "double_click",
        "Double click",
        FB_CMD_GET_DOUBLE_CLICK_MBB,
        sizeof(FB_CMD_GET_DOUBLE_CLICK_MBB),
        NULL,
        0,
        0x01,
        0x20,
        0x1F,
        5,
    },
    {
        "triple_click",
        "Triple click",
        FB_CMD_GET_TRIPLE_CLICK,
        sizeof(FB_CMD_GET_TRIPLE_CLICK),
        NULL,
        0,
        0x01,
        0x26,
        0x25,
        4,
    },
    {
        "light_hold",
        "Light hold",
        FB_CMD_GET_LIGHT_HOLD,
        sizeof(FB_CMD_GET_LIGHT_HOLD),
        NULL,
        0,
        0x2B,
        0x93,
        0x92,
        -1,
    },
};

const size_t FB_GESTURE_COUNT = 6;

int fb_gesture_index(const char *key)
{
    size_t i;
    for (i = 0; i < FB_GESTURE_COUNT; i++)
    {
        if (strcmp(FB_GESTURES[i].key, key) == 0)
            return (int)i;
    }
    return -1;
}

int fb_gesture_from_alias(const char *alias)
{
    int i;
    for (i = 0; i < (int)FB_GESTURE_COUNT; i++)
    {
        if (strcmp(FB_GESTURES[i].key, alias) == 0)
            return i;
    }
    for (i = 0; FB_GESTURE_ALIASES[i].key; i++)
    {
        if (strcmp(FB_GESTURE_ALIASES[i].alias, alias) == 0)
            return fb_gesture_index(FB_GESTURE_ALIASES[i].key);
    }
    return -1;
}

const char *fb_gesture_name(int g)
{
    if (g < 0 || (size_t)g >= FB_GESTURE_COUNT)
        return NULL;
    return FB_GESTURES[g].name;
}

int fb_gesture_nc_action(int g)
{
    if (g < 0 || (size_t)g >= FB_GESTURE_COUNT)
        return -1;
    return FB_GESTURES[g].nc_action;
}

const fb_feature FB_FEATURABLE[14] = {
    {"greet", "Voice prompts", "Greet (voice prompt)", FB_CMD_GET_GREET, sizeof(FB_CMD_GET_GREET), NULL, 0, 0x2B, 0x0F, 0x0E},
    {"wear", "Wear detection", "Wear detection", FB_CMD_GET_WEAR, sizeof(FB_CMD_GET_WEAR), NULL, 0, 0x2B, 0x11, 0x10},
    {"ivol", "Intellect volume", "Intellect volume", FB_CMD_GET_INTELLECT_VOLUME, sizeof(FB_CMD_GET_INTELLECT_VOLUME), NULL, 0, 0x2B, 0x23, 0x22},
    {"save", "Saving mode", "Saving mode", FB_CMD_GET_SAVING_MODE, sizeof(FB_CMD_GET_SAVING_MODE), NULL, 0, 0x2B, 0x1D, 0x1C},
    {"glat", "Game low latency", "Game low latency", FB_CMD_GET_GAME_LOW_LATENCY, sizeof(FB_CMD_GET_GAME_LOW_LATENCY), NULL, 0, 0x2B, 0x6C, 0x6C},
    {"dual", "Dual connect", "Dual connect", FB_CMD_GET_DUAL_CONNECT, sizeof(FB_CMD_GET_DUAL_CONNECT), NULL, 0, 0x2B, 0x2F, 0x2E},
    {"trans", "Translate mode", "Translate mode", FB_CMD_GET_TRANSLATE_MODE, sizeof(FB_CMD_GET_TRANSLATE_MODE), NULL, 0, 0x2B, 0x4D, 0x4C},
    {"venh", "Voice enhance", "Voice enhance", FB_CMD_GET_VOICE_ENHANCE, sizeof(FB_CMD_GET_VOICE_ENHANCE), NULL, 0, 0x2B, 0x42, 0x41},
    {"32k", "32K HD voice", "32K HD voice", FB_CMD_GET_32K_HD, sizeof(FB_CMD_GET_32K_HD), NULL, 0, 0x2B, 0x46, 0x45},
    {"hd", "HD sound switch", "HD sound switch", FB_CMD_GET_HD_SWITCH, sizeof(FB_CMD_GET_HD_SWITCH), NULL, 0, 0x2B, 0x5E, 0x5D},
    {"lre", "L/R ear recognition", "L/R ear recognition", FB_CMD_GET_LEFT_RIGHT_EAR, sizeof(FB_CMD_GET_LEFT_RIGHT_EAR), NULL, 0, 0x2B, 0x9A, 0x99},
    {"wind", "Wind mode", "Wind mode", FB_CMD_GET_WIND_MODE, sizeof(FB_CMD_GET_WIND_MODE), NULL, 0, 0x2B, 0x95, 0x94},
    {"silent", "Silent upgrade", "Silent upgrade", FB_CMD_GET_SILENT_UPGRADE, sizeof(FB_CMD_GET_SILENT_UPGRADE), NULL, 0, 0x2B, 0x70, 0x6F},
    {"health", "Health alerts", "Health alerts", FB_CMD_GET_HEALTH_ALERTS, sizeof(FB_CMD_GET_HEALTH_ALERTS), NULL, 0, 0x2B, 0x61, 0x60},
};

const size_t FB_FEATURABLE_COUNT = 14;
