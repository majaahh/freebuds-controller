/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.majaahh.freebuds.controller.MainViewModel
import com.majaahh.freebuds.controller.data.ScannedDevice

@Composable
fun ConnectScreen(vm: MainViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(24.dp))

        Text(
            text = "FreeBuds",
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = "Remote control for your Huawei FreeBuds.\n"
                + "The Python backend (freebuds_server.py) does the Bluetooth talk — "
                + "this app just points at it.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Backend server", style = MaterialTheme.typography.titleMedium)

                OutlinedTextField(
                    value = vm.host,
                    onValueChange = { vm.host = it },
                    label = { Text("Host (IP of the machine running the script)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = vm.port,
                    onValueChange = { vm.port = it },
                    label = { Text("Port") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = vm.mac,
                    onValueChange = { vm.mac = it },
                    label = { Text("Buds MAC address (AA:BB:CC:DD:EE:FF)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(
                        onClick = { vm.connect() },
                        enabled = !vm.busy,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (vm.busy) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.width(8.dp))
                        }
                        Text(if (vm.busy) "Connecting…" else "Connect")
                    }
                    OutlinedButton(onClick = { vm.scan() }, enabled = !vm.scanning) {
                        Text(if (vm.scanning) "Scanning…" else "Scan")
                    }
                }
            }
        }

        if (vm.devices.isNotEmpty()) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Found", style = MaterialTheme.typography.titleSmall)
                    vm.devices.forEach { d ->
                        DeviceRow(d) { vm.useDevice(d) }
                        HorizontalDivider()
                    }
                }
            }
        }

        Spacer(Modifier.height(8.dp))
        Text(
            text = "Quick start:\n"
                + "  1. On the host machine (Linux, with Bluetooth):\n"
                + "     python3 freebuds_server.py --host 0.0.0.0\n"
                + "  2. Put the FreeBuds in pairing mode, tap Scan, pick your buds.\n"
                + "  3. Tap Connect. The buds talk to the host; you control them here.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun DeviceRow(d: ScannedDevice, onPick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(d.name, style = MaterialTheme.typography.bodyLarge)
            Text(
                d.address + (d.rssi?.let { "  •  ${it} dBm" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        TextButton(onClick = onPick) { Text("Use") }
    }
}
