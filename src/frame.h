/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef FB_FRAME_H
#define FB_FRAME_H

#include <stddef.h>
#include <stdint.h>

#define FB_SPP_CHANNEL 16

#define FB_SIDE_LEFT 1
#define FB_SIDE_RIGHT 2

typedef struct
{
    uint8_t *payload;
    size_t payload_len;
    uint8_t *data;
    size_t data_len;
    uint8_t svc;
    uint8_t cmd;
    int crc_ok;
} fb_frame;

typedef struct
{
    fb_frame *items;
    size_t count;
} fb_frames;

typedef struct
{
    uint8_t tag;
    uint8_t len;
    uint8_t *value;
} fb_tlv;

typedef struct
{
    fb_tlv *items;
    size_t count;
} fb_tlvs;

uint8_t *fb_build_frame(const uint8_t *payload, size_t payload_len, size_t *out_len);
fb_frames *fb_parse_frames(const uint8_t *data, size_t len);
fb_tlvs fb_parse_tlv(const uint8_t *data, size_t len);
void fb_tlvs_free(fb_tlvs *tlvs);
void fb_frames_free(fb_frames *frames);

#endif