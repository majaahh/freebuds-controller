/*
 * Copyright (c) 2026 Majaahh
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

package com.majaahh.freebuds.controller

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.majaahh.freebuds.controller.ui.ConnectScreen
import com.majaahh.freebuds.controller.ui.DashboardScreen
import com.majaahh.freebuds.controller.ui.theme.FreeBudsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            FreeBudsTheme {
                App()
            }
        }
    }
}

@Composable
private fun App(vm: MainViewModel = viewModel()) {
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(vm.message) {
        val msg = vm.message ?: return@LaunchedEffect
        snackbarHostState.showSnackbar(msg)
        vm.message = null
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { padding ->
        Box(Modifier.padding(padding)) {
            if (vm.connected) {
                DashboardScreen(vm)
            } else {
                ConnectScreen(vm)
            }
        }
    }
}
