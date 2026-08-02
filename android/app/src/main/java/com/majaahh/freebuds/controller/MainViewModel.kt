/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.majaahh.freebuds.controller.data.Api
import com.majaahh.freebuds.controller.data.AncState
import com.majaahh.freebuds.controller.data.Battery
import com.majaahh.freebuds.controller.data.DeviceInfo
import com.majaahh.freebuds.controller.data.FeatureState
import com.majaahh.freebuds.controller.data.GestureState
import com.majaahh.freebuds.controller.data.Meta
import com.majaahh.freebuds.controller.data.Parsers
import com.majaahh.freebuds.controller.data.ScannedDevice
import com.majaahh.freebuds.controller.data.SfxState
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = app.getSharedPreferences("freebuds", Context.MODE_PRIVATE)

    var host by mutableStateOf(prefs.getString("host", "") ?: "")
    var port by mutableStateOf(prefs.getString("port", "8765") ?: "8765")
    var mac by mutableStateOf(prefs.getString("mac", "") ?: "")

    var connected by mutableStateOf(false)
    var busy by mutableStateOf(false)
    var scanning by mutableStateOf(false)
    var devices by mutableStateOf<List<ScannedDevice>>(emptyList())

    var meta by mutableStateOf<Meta?>(null)
    var deviceInfo by mutableStateOf<DeviceInfo?>(null)
    var battery by mutableStateOf<Battery?>(null)
    var anc by mutableStateOf<AncState?>(null)
    var gestures by mutableStateOf<Map<String, GestureState>>(emptyMap())
    var features by mutableStateOf<Map<String, FeatureState>>(emptyMap())
    var sfx by mutableStateOf<SfxState?>(null)

    var message by mutableStateOf<String?>(null)

    fun showMessage(msg: String) {
        message = msg
    }

    private fun applyBase() {
        Api.baseUrl = "http://${host.trim()}:${port.trim().ifEmpty { "8765" }}"
        prefs.edit().putString("host", host).putString("port", port).apply()
    }

    fun connect() {
        if (busy) return
        applyBase()
        if (mac.isBlank()) {
            showMessage("Enter the buds MAC address (e.g. AA:BB:CC:DD:EE:FF)")
            return
        }
        busy = true
        viewModelScope.launch {
            try {
                val resp = Api.post("/api/connect", JSONObject().put("mac", mac.trim()))
                if (resp.optBoolean("connected", false)) {
                    prefs.edit().putString("mac", mac).apply()
                    connected = true
                    showMessage("Connected to ${mac.trim()}")
                    loadMeta()
                    refresh()
                } else {
                    showMessage(resp.optString("error", "Connect failed"))
                }
            } catch (e: Exception) {
                showMessage("Connect failed: ${e.message}")
            } finally {
                busy = false
            }
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            try {
                Api.post("/api/disconnect")
            } catch (_: Exception) {
            }
            connected = false
            battery = null
            anc = null
            gestures = emptyMap()
            features = emptyMap()
            sfx = null
            deviceInfo = null
        }
    }

    fun loadMeta() {
        viewModelScope.launch {
            try {
                meta = Parsers.meta(Api.get("/api/meta"))
            } catch (e: Exception) {
                showMessage("Could not load device metadata: ${e.message}")
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            busy = true
            try {
                val info = Api.get("/api/info").optJSONObject("info") ?: JSONObject()
                battery = Parsers.battery(info.optJSONObject("battery"))
                anc = Parsers.anc(info.optJSONObject("anc"))
                deviceInfo = Parsers.version(info.optJSONObject("version"))
                gestures = gesturesOf(info, meta)
                features = featuresOf(info)
                sfx = Parsers.sfx(info.optJSONObject("sound_effect"))
            } catch (e: Exception) {
                showMessage("Refresh failed: ${e.message}")
                connected = false
            } finally {
                busy = false
            }
        }
    }

    fun scan() {
        if (scanning || busy) return
        applyBase()
        scanning = true
        devices = emptyList()
        viewModelScope.launch {
            try {
                val resp = Api.get("/api/scan?time=5")
                val arr = resp.optJSONArray("devices") ?: org.json.JSONArray()
                devices = (0 until arr.length()).map { i ->
                    val d = arr.optJSONObject(i)
                    ScannedDevice(
                        name = d?.optString("name") ?: "FreeBuds",
                        address = d?.optString("address") ?: "",
                        rssi = d?.optInt("rssi", -1)?.takeIf { it != -1 },
                    )
                }
                if (devices.isEmpty()) showMessage("No FreeBuds found — put them in pairing mode")
            } catch (e: Exception) {
                showMessage("Scan failed: ${e.message}")
            } finally {
                scanning = false
            }
        }
    }

    fun setAnc(mode: Int, level: Int? = null) {
        viewModelScope.launch {
            try {
                val payload = JSONObject().put("mode", mode)
                if (level != null) payload.put("level", level)
                Api.post("/api/anc", payload)
                val m = meta
                anc = AncState(
                    mode = mode,
                    modeName = m?.ncModes?.get(mode),
                    level = level,
                    levelName = level?.let { m?.ncLevels?.get(it) },
                )
            } catch (e: Exception) {
                showMessage("Noise control failed: ${e.message}")
            }
        }
    }

    fun setGesture(key: String, side: Int, action: Int) {
        viewModelScope.launch {
            try {
                val payload = JSONObject()
                    .put("gesture", key)
                    .put("side", side)
                    .put("action", action)
                Api.post("/api/gesture", payload)
                val g = gestures[key] ?: GestureState(null, null, emptyList())
                gestures = gestures + (
                    key to if (side == 1) g.copy(left = action) else g.copy(right = action)
                    )
            } catch (e: Exception) {
                showMessage("Gesture update failed: ${e.message}")
            }
        }
    }

    fun setFeature(name: String, enabled: Boolean) {
        viewModelScope.launch {
            try {
                Api.post("/api/feature", JSONObject().put("name", name).put("enabled", enabled))
                features = features + (name to FeatureState(enabled))
            } catch (e: Exception) {
                showMessage("Feature update failed: ${e.message}")
            }
        }
    }

    fun setSfx(mode: Int) {
        viewModelScope.launch {
            try {
                Api.post("/api/sfx", JSONObject().put("mode", mode))
                val m = meta
                sfx = SfxState(mode, m?.eqModes?.get(mode))
            } catch (e: Exception) {
                showMessage("Sound effect failed: ${e.message}")
            }
        }
    }

    fun useDevice(d: ScannedDevice) {
        mac = d.address
    }
}

private fun gesturesOf(info: JSONObject, meta: Meta?): Map<String, GestureState> =
    buildMap {
        meta?.gestures?.keys?.forEach { key ->
            put(key, Parsers.gesture(info.optJSONObject(key)))
        }
    }

private fun featuresOf(info: JSONObject): Map<String, FeatureState> = buildMap {
    val it = info.keys()
    while (it.hasNext()) {
        val key = it.next()
        val value = info.optJSONObject(key) ?: continue
        if (value.has("enabled")) put(key, Parsers.feature(value))
    }
}
