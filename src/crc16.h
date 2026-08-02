/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef FB_CRC16_H
#define FB_CRC16_H

#include <stddef.h>
#include <stdint.h>

uint16_t fb_crc16(const uint8_t *data, size_t len);

#endif