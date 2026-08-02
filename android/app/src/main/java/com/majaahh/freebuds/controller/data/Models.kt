/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller.data

import org.json.JSONObject

data class Meta(
    val ncModes: Map<Int, String>,
    val ncLevels: Map<Int, String>,
    val eqModes: Map<Int, String>,
    val gestures: Map<String, GestureMeta>,
    val features: Map<String, FeatureMeta>,
)

data class GestureMeta(
    val key: String,
    val name: String,
    val actions: Map<Int, String>,
)

data class FeatureMeta(val key: String, val name: String, val settable: Boolean)

data class Battery(val left: Int?, val right: Int?, val box: Int?)

data class AncState(
    val mode: Int?,
    val modeName: String?,
    val level: Int?,
    val levelName: String?,
)

data class GestureState(
    val left: Int?,
    val right: Int?,
    val supported: List<Int>,
)

data class FeatureState(val enabled: Boolean?)

data class SfxState(val mode: Int?, val modeName: String?)

data class DeviceInfo(val model: String?, val firmware: String?)

data class ScannedDevice(val name: String, val address: String, val rssi: Int?)

object Parsers {

    fun meta(o: JSONObject): Meta = Meta(
        ncModes = stringMap(o.optJSONObject("nc_modes")),
        ncLevels = stringMap(o.optJSONObject("nc_levels")),
        eqModes = stringMap(o.optJSONObject("eq_modes")),
        gestures = run {
            val g = o.optJSONObject("gestures") ?: JSONObject()
            val out = LinkedHashMap<String, GestureMeta>()
            val it = g.keys()
            while (it.hasNext()) {
                val key = it.next()
                val entry = g.optJSONObject(key) ?: continue
                out[key] = GestureMeta(
                    key = key,
                    name = entry.optString("name", key),
                    actions = stringMap(entry.optJSONObject("actions")),
                )
            }
            out
        },
        features = run {
            val f = o.optJSONObject("features") ?: JSONObject()
            val out = LinkedHashMap<String, FeatureMeta>()
            val it = f.keys()
            while (it.hasNext()) {
                val key = it.next()
                val entry = f.optJSONObject(key) ?: continue
                out[key] = FeatureMeta(
                    key = key,
                    name = entry.optString("name", key),
                    settable = entry.optBoolean("settable", false),
                )
            }
            out
        },
    )

    fun battery(o: JSONObject?): Battery? = o?.let {
        Battery(
            left = it.optInt("left_battery", -1).takeIf { v -> v >= 0 },
            right = it.optInt("right_battery", -1).takeIf { v -> v >= 0 },
            box = it.optInt("box_battery", -1).takeIf { v -> v >= 0 },
        )
    }

    fun anc(o: JSONObject?): AncState? = o?.let {
        AncState(
            mode = if (it.has("mode")) it.optInt("mode") else null,
            modeName = it.optString("mode_name").ifBlank { null },
            level = if (it.has("level")) it.optInt("level") else null,
            levelName = it.optString("level_name").ifBlank { null },
        )
    }

    fun gesture(o: JSONObject?): GestureState = GestureState(
        left = if (o?.has("left") == true) o.optInt("left") else null,
        right = if (o?.has("right") == true) o.optInt("right") else null,
        supported = o?.optJSONArray("supported")?.let { arr ->
            (0 until arr.length()).mapNotNull { i -> arr.optInt(i).takeIf { it != 255 } }
        } ?: emptyList(),
    )

    fun feature(o: JSONObject?): FeatureState = FeatureState(
        enabled = if (o?.has("enabled") == true) o.optBoolean("enabled") else null,
    )

    fun sfx(o: JSONObject?): SfxState? = o?.let {
        SfxState(
            mode = if (it.has("mode")) it.optInt("mode") else null,
            modeName = it.optString("mode_name").ifBlank { null },
        )
    }

    fun version(o: JSONObject?): DeviceInfo = DeviceInfo(
        model = o?.optString("model")?.ifBlank { null },
        firmware = o?.optString("firmware")?.ifBlank { null },
    )

    private fun stringMap(o: JSONObject?): Map<Int, String> = buildMap {
        if (o == null) return@buildMap
        val it = o.keys()
        while (it.hasNext()) {
            val k = it.next()
            val num = k.toIntOrNull() ?: continue
            put(num, o.optString(k, k))
        }
    }
}
