package com.insightfulgames.app.data.repository

import com.insightfulgames.app.data.model.HomeDto
import com.insightfulgames.app.data.model.ProfileDto
import com.insightfulgames.app.data.model.StatsDto
import com.insightfulgames.app.data.remote.ApiService
import com.insightfulgames.app.data.remote.apiCall

class ProfileRepository(private val api: ApiService) {
    suspend fun home(): Result<HomeDto> = apiCall { api.home() }
    suspend fun profile(): Result<ProfileDto> = apiCall { api.profile() }
    suspend fun stats(): Result<StatsDto> = apiCall { api.stats() }
}
