/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cli.h"

static void usage(void) {
  printf("Usage: freebuds <command> [options]\n\n");
  printf("Commands:\n");
  printf("  scan [-t <seconds>] [--save <path>]   Scan for FreeBuds via "
         "bluetoothctl\n");
  printf("  run [-a <mac>] [-t <timeout>] <cmds>  Connect and run commands\n");
  printf("  run --help                            Show available commands\n");
  printf("\n");
  printf("Global options:\n");
  printf("  -h, --help   Show this help\n");
}

int main(int argc, char **argv) {
  const char *address = NULL;
  double timeout = 10.0;
  int time_sec = 8;
  const char *save_path = NULL;
  int i;

  if (argc < 2) {
    usage();
    return 1;
  }

  if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {
    usage();
    return 0;
  }

  if (strcmp(argv[1], "scan") == 0) {
    for (i = 2; i < argc; i++) {
      if (strcmp(argv[i], "-t") == 0 && i + 1 < argc)
        time_sec = atoi(argv[++i]);
      else if (strcmp(argv[i], "--save") == 0 && i + 1 < argc)
        save_path = argv[++i];
    }
    fb_cmd_scan(time_sec, save_path);
    return 0;
  }

  if (strcmp(argv[1], "run") == 0) {
    int cmd_start = -1;
    for (i = 2; i < argc; i++) {
      if (strcmp(argv[i], "-a") == 0 && i + 1 < argc)
        address = argv[++i];
      else if (strcmp(argv[i], "-t") == 0 && i + 1 < argc)
        timeout = atof(argv[++i]);
      else if (cmd_start < 0)
        cmd_start = i;
    }
    if (cmd_start < 0) {
      print_run_help();
      return 0;
    }
    return fb_cmd_run(address, timeout, argc - cmd_start, argv + cmd_start);
  }

  printf("Unknown command '%s'\n\n", argv[1]);
  usage();
  return 1;
}
