/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.majaahh.freebuds.controller.MainViewModel
import com.majaahh.freebuds.controller.data.Battery
import com.majaahh.freebuds.controller.data.FeatureMeta
import com.majaahh.freebuds.controller.data.FeatureState
import com.majaahh.freebuds.controller.data.GestureMeta
import com.majaahh.freebuds.controller.data.GestureState

@Composable
fun DashboardScreen(vm: MainViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { HeaderCard(vm) }

        vm.battery?.let { b ->
            item { BatteryCard(b) }
        }

        vm.anc?.let {
            item { AncCard(vm) }
        }

        vm.sfx?.let {
            item { SfxCard(vm) }
        }

        val gestureList = vm.meta?.gestures?.values?.toList() ?: emptyList()
        if (gestureList.isNotEmpty()) {
            item {
                GesturesCard(
                    gestures = gestureList,
                    current = vm.gestures,
                    onSet = { key, side, action -> vm.setGesture(key, side, action) },
                )
            }
        }

        val features = vm.meta?.features?.values?.filter { it.settable } ?: emptyList()
        if (features.isNotEmpty()) {
            item {
                FeaturesCard(
                    features = features,
                    current = vm.features,
                    onToggle = { name, enabled -> vm.setFeature(name, enabled) },
                )
            }
        }
    }
}

@Composable
private fun HeaderCard(vm: MainViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    text = vm.deviceInfo?.model ?: "FreeBuds",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = buildString {
                        append("Connected")
                        vm.deviceInfo?.firmware?.let { append("  •  FW $it") }
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (vm.busy) {
                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(12.dp))
            }
            OutlinedButton(onClick = { vm.refresh() }, enabled = !vm.busy) {
                Text("Refresh")
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = { vm.disconnect() }) {
                Text("Disconnect")
            }
        }
    }
}

@Composable
private fun BatteryCard(battery: Battery) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Battery", style = MaterialTheme.typography.titleMedium)
            BatteryRow("Left", battery.left)
            BatteryRow("Right", battery.right)
            BatteryRow("Case", battery.box)
        }
    }
}

@Composable
private fun BatteryRow(label: String, value: Int?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.width(56.dp), style = MaterialTheme.typography.bodyMedium)
        LinearProgressIndicator(
            progress = { (value ?: 0) / 100f },
            modifier = Modifier.weight(1f).height(8.dp),
        )
        Spacer(Modifier.width(12.dp))
        Text(
            text = value?.let { "$it%" } ?: "—",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun AncCard(vm: MainViewModel) {
    val meta = vm.meta ?: return
    val anc = vm.anc ?: return
    val modes = meta.ncModes.entries.toList()
    val modeIdx = anc.mode?.let { m -> modes.indexOfFirst { it.key == m } } ?: -1

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Noise control", style = MaterialTheme.typography.titleMedium)

            if (modes.size > 1) {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    modes.forEachIndexed { i, (value, label) ->
                        SegmentedButton(
                            selected = i == modeIdx,
                            onClick = { vm.setAnc(value) },
                            shape = SegmentedButtonDefaults.itemShape(index = i, count = modes.size),
                        ) { Text(label) }
                    }
                }
            }

            if (anc.mode == 1 && meta.ncLevels.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        "Level",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        meta.ncLevels.forEach { (value, label) ->
                            FilterChip(
                                selected = anc.level == value,
                                onClick = { vm.setAnc(1, value) },
                                label = { Text(label) },
                            )
                        }
                    }
                }
            }

            anc.levelName?.let {
                Text(
                    "Active: ${anc.modeName ?: "?"}" + if (anc.level != null) " • ${anc.levelName}" else "",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun SfxCard(vm: MainViewModel) {
    val meta = vm.meta ?: return
    val sfx = vm.sfx ?: return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Sound effect", style = MaterialTheme.typography.titleMedium)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                meta.eqModes.forEach { (value, label) ->
                    FilterChip(
                        selected = sfx.mode == value,
                        onClick = { vm.setSfx(value) },
                        label = { Text(label) },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GesturesCard(
    gestures: List<GestureMeta>,
    current: Map<String, GestureState>,
    onSet: (key: String, side: Int, action: Int) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Gestures", style = MaterialTheme.typography.titleMedium)
            Text(
                "Assign an action to each gesture, per ear.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(4.dp))

            gestures.forEach { g ->
                val state = current[g.key] ?: GestureState(null, null, emptyList())
                GestureRow(g, state) { side, action -> onSet(g.key, side, action) }
                HorizontalDivider(Modifier.padding(vertical = 6.dp))
            }
        }
    }
}

@Composable
private fun GestureRow(
    g: GestureMeta,
    state: GestureState,
    onSet: (side: Int, action: Int) -> Unit,
) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(g.name, style = MaterialTheme.typography.titleSmall)

        if (g.actions.isEmpty()) {
            Text(
                "No configurable actions reported by the device.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ActionDropdown(
                label = "Left",
                actions = g.actions,
                selected = state.left,
                modifier = Modifier.weight(1f),
            ) { onSet(1, it) }
            ActionDropdown(
                label = "Right",
                actions = g.actions,
                selected = state.right,
                modifier = Modifier.weight(1f),
            ) { onSet(2, it) }
        }
    }
}

@Composable
private fun ActionDropdown(
    label: String,
    actions: Map<Int, String>,
    selected: Int?,
    modifier: Modifier = Modifier,
    onSelect: (Int) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }

    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selected?.let { actions[it] ?: "Action $it" } ?: "—",
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            actions.forEach { (value, name) ->
                DropdownMenuItem(
                    text = { Text(name) },
                    onClick = {
                        expanded = false
                        onSelect(value)
                    },
                )
            }
        }
    }
}

@Composable
private fun FeaturesCard(
    features: List<FeatureMeta>,
    current: Map<String, FeatureState>,
    onToggle: (name: String, enabled: Boolean) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Features", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            features.forEach { f ->
                val enabled = current[f.key]?.enabled
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        f.name,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.weight(1f),
                    )
                    Switch(
                        checked = enabled == true,
                        onCheckedChange = { onToggle(f.key, it) },
                        enabled = enabled != null,
                    )
                }
            }
        }
    }
}
