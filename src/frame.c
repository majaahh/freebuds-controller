/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdlib.h>
#include <string.h>

#include "crc16.h"
#include "frame.h"

uint8_t *fb_build_frame(const uint8_t *payload, size_t payload_len, size_t *out_len)
{
    size_t frame_len = payload_len + 1;
    size_t total = 4 + payload_len + 2;
    uint8_t *frame = malloc(total);
    uint16_t crc;

    if (!frame)
    {
        *out_len = 0;
        return NULL;
    }

    frame[0] = 0x5A;
    frame[1] = (uint8_t)((frame_len >> 8) & 0xFF);
    frame[2] = (uint8_t)(frame_len & 0xFF);
    frame[3] = 0x00;
    if (payload_len > 0)
        memcpy(frame + 4, payload, payload_len);

    crc = fb_crc16(frame, 4 + payload_len);
    frame[4 + payload_len] = (uint8_t)((crc >> 8) & 0xFF);
    frame[4 + payload_len + 1] = (uint8_t)(crc & 0xFF);

    *out_len = total;
    return frame;
}

fb_frames *fb_parse_frames(const uint8_t *data, size_t len)
{
    fb_frames *frames = calloc(1, sizeof(fb_frames));
    size_t offset = 0;

    while (offset < len)
    {
        const uint8_t *remaining;
        size_t rem_len;
        size_t frame_len, total;
        fb_frame *f;

        if (data[offset] != 0x5A)
        {
            offset += 1;
            continue;
        }

        remaining = data + offset;
        rem_len = len - offset;
        if (rem_len < 4)
            break;

        frame_len = ((size_t)remaining[1] << 8) | remaining[2];
        total = 4 + (frame_len - 1) + 2;
        if (rem_len < total)
            break;

        frames->items = realloc(frames->items, (frames->count + 1) * sizeof(fb_frame));
        f = &frames->items[frames->count];
        memset(f, 0, sizeof(fb_frame));

        f->payload = malloc(frame_len - 1);
        memcpy(f->payload, remaining + 4, frame_len - 1);
        f->payload_len = frame_len - 1;
        f->data = (f->payload_len > 2) ? f->payload + 2 : NULL;
        f->data_len = (f->payload_len > 2) ? f->payload_len - 2 : 0;
        f->svc = f->payload_len > 0 ? f->payload[0] : 0;
        f->cmd = f->payload_len > 1 ? f->payload[1] : 0;

        {
            uint16_t crc_recv = (uint16_t)(((uint16_t)remaining[total - 2] << 8) | remaining[total - 1]);
            uint16_t crc_calc = fb_crc16(remaining, total - 2);
            f->crc_ok = crc_recv == crc_calc;
        }

        frames->count++;
        offset += total;
    }

    return frames;
}

fb_tlvs fb_parse_tlv(const uint8_t *data, size_t len)
{
    fb_tlvs tlvs = {0};
    size_t pos = 0;

    while (pos + 1 < len)
    {
        uint8_t tag = data[pos];
        size_t length = data[pos + 1];

        if (pos + 2 + length > len)
            break;

        tlvs.items = realloc(tlvs.items, (tlvs.count + 1) * sizeof(fb_tlv));
        tlvs.items[tlvs.count].tag = tag;
        tlvs.items[tlvs.count].len = (uint8_t)length;
        tlvs.items[tlvs.count].value = (uint8_t *)data + pos + 2;
        tlvs.count++;
        pos += 2 + length;
    }

    return tlvs;
}

void fb_tlvs_free(fb_tlvs *tlvs)
{
    if (tlvs->items)
        free(tlvs->items);
    tlvs->items = NULL;
    tlvs->count = 0;
}

void fb_frames_free(fb_frames *frames)
{
    size_t i;

    if (!frames)
        return;
    for (i = 0; i < frames->count; i++)
    {
        if (frames->items[i].payload)
            free(frames->items[i].payload);
    }
    free(frames->items);
    free(frames);
}