/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class ApiException(message: String, val code: Int = -1) : Exception(message)

object Api {
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(90, TimeUnit.SECONDS)
        .build()

    @Volatile
    var baseUrl: String = "http://127.0.0.1:8765"

    private fun url(path: String) = baseUrl.trimEnd('/') + path

    suspend fun get(path: String): JSONObject = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url(path)).get().build()
        client.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw ApiException(body.ifEmpty { "HTTP ${resp.code}" }, resp.code)
            JSONObject(body)
        }
    }

    suspend fun post(path: String, payload: JSONObject = JSONObject()): JSONObject =
        withContext(Dispatchers.IO) {
            val req = Request.Builder()
                .url(url(path))
                .post(payload.toString().toRequestBody(jsonType))
                .build()
            client.newCall(req).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                if (!resp.isSuccessful) throw ApiException(body.ifEmpty { "HTTP ${resp.code}" }, resp.code)
                JSONObject(body)
            }
        }
}
