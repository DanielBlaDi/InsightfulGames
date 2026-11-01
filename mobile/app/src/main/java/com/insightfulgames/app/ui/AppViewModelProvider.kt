package com.insightfulgames.app.ui

import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.insightfulgames.app.AppContainer
import com.insightfulgames.app.InsightfulApp
import com.insightfulgames.app.ui.login.LoginViewModel
import com.insightfulgames.app.ui.profile.ProfileViewModel

fun CreationExtras.container(): AppContainer =
    (this[APPLICATION_KEY] as InsightfulApp).container

object AppViewModelProvider {
    val Factory = viewModelFactory {
        initializer { LoginViewModel(container().authRepository) }
        initializer { ProfileViewModel(container().statsRepository, container().authRepository) }
    }
}
