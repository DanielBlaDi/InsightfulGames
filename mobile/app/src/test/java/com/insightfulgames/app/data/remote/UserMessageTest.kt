package com.insightfulgames.app.data.remote

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UserMessageTest {
    private fun msg(status: Int, code: String, raw: String = "mensaje crudo del servidor") =
        ApiException(status, code, raw).userMessage()

    @Test fun profileNotFoundIsUnavailableNotSessionExpiredNorRaw() {
        val m = msg(404, "PROFILE_NOT_FOUND", "Perfil inexistente")
        assertEquals("No disponible en este momento.", m)
        assertFalse(ApiException(404, "PROFILE_NOT_FOUND", "x").isUnauthorized)
    }

    @Test fun unauthorizedMeansSessionExpired() {
        assertTrue(ApiException(401, "UNAUTHORIZED", "x").isUnauthorized)
        assertEquals("Tu sesión expiró. Inicia sesión de nuevo.", msg(401, "UNAUTHORIZED"))
    }

    @Test fun catalogCodesHaveFriendlyText() {
        assertEquals("Usuario o contraseña incorrectos.", msg(401, "INVALID_CREDENTIALS"))
        assertEquals("Ese nombre de usuario ya existe.", msg(409, "USERNAME_TAKEN"))
        assertEquals("El servidor no está disponible. Inténtalo más tarde.", msg(503, "SERVICES_UNAVAILABLE"))
        assertEquals("La partida no existe o ya no es visible.", msg(404, "GAME_NOT_FOUND"))
        assertEquals("La partida no existe o ya no es visible.", msg(404, "MATCH_NOT_FOUND"))
    }

    @Test fun retiredCodeIsNoLongerTranslated() {
        // Contrato 4.5: SERVICE_UNAVAILABLE dejó de usarse; solo existe SERVICES_UNAVAILABLE.
        assertEquals("mensaje crudo del servidor", msg(503, "SERVICE_UNAVAILABLE"))
    }
}
