package com.insightfulgames.app.ui

import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.insightfulgames.app.AppContainer
import com.insightfulgames.app.InsightfulApp
import com.insightfulgames.app.ui.auth.AuthViewModel
import com.insightfulgames.app.ui.history.HistoryViewModel
import com.insightfulgames.app.ui.home.HomeViewModel
import com.insightfulgames.app.ui.profile.ProfileViewModel
import com.insightfulgames.app.ui.stats.StatsViewModel

fun CreationExtras.container(): AppContainer =
    (this[APPLICATION_KEY] as InsightfulApp).container

object AppViewModelProvider {
    val Factory = viewModelFactory {
        initializer { AuthViewModel(container().authRepository) }
        initializer { HomeViewModel(container().profileRepository) }
        initializer { ProfileViewModel(container().profileRepository, container().authRepository) }
        initializer { StatsViewModel(container().profileRepository) }
        initializer { HistoryViewModel(container().gameRepository) }
    }
}
