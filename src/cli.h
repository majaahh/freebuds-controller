/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef FB_CLI_H
#define FB_CLI_H

#include "controller.h"

typedef struct {
  char name[128];
  char address[32];
  int rssi;
  int has_rssi;
} fb_scan_entry;

typedef struct {
  fb_scan_entry *items;
  size_t count;
} fb_scan_results;

void fb_scan_freebuds(fb_scan_results *out, int scan_time);
int fb_is_paired(const char *address);
int fb_save_mac(const char *mac, const char *path);
const char *fb_load_mac(const char *path, char *out, size_t outsz);

void print_run_help(void);

int fb_cmd_scan(int time_sec, const char *save_path);
int fb_cmd_run(const char *address, double timeout, int argc, char **argv);

#endif