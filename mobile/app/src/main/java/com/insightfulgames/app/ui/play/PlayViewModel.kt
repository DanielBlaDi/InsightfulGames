package com.insightfulgames.app.ui.play

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.remote.ApiException
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.GameRepository
import com.insightfulgames.app.ui.Square
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PlayUi(
    val game: GameStateDto? = null,
    /** Error al cargar la partida (pantalla completa con Reintentar). */
    val loadError: String? = null,
    /** Aviso pasajero (jugada rechazada, sin conexión...). */
    val notice: String? = null,
    val selected: Square? = null,
    /** Jugada de coronación esperando a que se elija la pieza. */
    val pendingPromotion: Pair<Square, Square>? = null,
    val sending: Boolean = false,
    val flipped: Boolean = false,
    /** true cuando la partida terminó mientras se jugaba en esta pantalla (para el diálogo de resultado). */
    val justFinished: Boolean = false,
)

/** Partida local en vivo: los dos colores se juegan en este teléfono. Cada jugada es un POST que devuelve el estado. */
class PlayViewModel(
    private val gameId: String,
    private val repo: GameRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow(PlayUi())
    val ui: StateFlow<PlayUi> = _ui.asStateFlow()

    private var expiryPoll: Job? = null

    init {
        load()
    }

    fun load() {
        _ui.update { it.copy(loadError = null) }
        viewModelScope.launch {
            repo.game(gameId)
                .onSuccess { game -> _ui.update { it.copy(game = game, selected = null) } }
                .onFailure { e -> _ui.update { it.copy(loadError = e.userMessage()) } }
        }
    }

    fun onSquare(square: Square) {
        val state = _ui.value
        val game = state.game ?: return
        if (state.sending || game.status != "in_progress") return
        when (val tap = MoveInput.onTap(game.legalMoves, game.fen, state.selected, square)) {
            is Tap.Select -> _ui.update { it.copy(selected = tap.square, notice = null) }
            Tap.Clear -> _ui.update { it.copy(selected = null) }
            is Tap.Move ->
                if (tap.needsPromotion) {
                    _ui.update { it.copy(pendingPromotion = tap.from to tap.to) }
                } else {
                    send(MoveInput.uci(tap.from, tap.to))
                }
        }
    }

    fun promote(piece: Char) {
        val (from, to) = _ui.value.pendingPromotion ?: return
        _ui.update { it.copy(pendingPromotion = null) }
        send(MoveInput.uci(from, to, piece))
    }

    fun cancelPromotion() = _ui.update { it.copy(pendingPromotion = null, selected = null) }

    fun flip() = _ui.update { it.copy(flipped = !it.flipped) }

    fun dismissNotice() = _ui.update { it.copy(notice = null) }

    fun dismissResult() = _ui.update { it.copy(justFinished = false) }

    /** Se rinde el color que tiene el turno. */
    fun resign() {
        val game = _ui.value.game ?: return
        val side = game.turn ?: return
        if (_ui.value.sending || game.status != "in_progress") return
        _ui.update { it.copy(sending = true, selected = null) }
        viewModelScope.launch {
            repo.resign(gameId, side)
                .onSuccess { applyState(it) }
                .onFailure { onActionFailed(it) }
            _ui.update { it.copy(sending = false) }
        }
    }

    /**
     * El reloj del que mueve llegó a 0 en pantalla. La partida la cierra el backend por tiempo:
     * se relee cada 2 s hasta verla terminada (con un límite, por si el reloj del teléfono adelanta).
     */
    fun onClockExpired() {
        if (expiryPoll?.isActive == true) return
        expiryPoll = viewModelScope.launch {
            repeat(EXPIRY_POLLS) {
                repo.game(gameId).onSuccess { applyState(it) }
                if (_ui.value.game?.status == "finished") return@launch
                delay(2_000)
            }
        }
    }

    private fun send(uci: String) {
        val game = _ui.value.game ?: return
        _ui.update { it.copy(sending = true, selected = null, notice = null) }
        viewModelScope.launch {
            repo.move(gameId, uci, game.version)
                .onSuccess { applyState(it) }
                .onFailure { onActionFailed(it) }
            _ui.update { it.copy(sending = false) }
        }
    }

    private fun applyState(next: GameStateDto) {
        _ui.update {
            val finishedNow = it.game?.status == "in_progress" && next.status == "finished"
            it.copy(game = next, justFinished = it.justFinished || finishedNow)
        }
    }

    /** Jugada o rendición rechazada: se avisa y, si el estado pudo cambiar, se relee la partida. */
    private suspend fun onActionFailed(error: Throwable) {
        _ui.update { it.copy(notice = error.userMessage()) }
        val code = (error as? ApiException)?.code
        if (code in RELOAD_CODES) {
            repo.game(gameId).onSuccess { applyState(it) }
        }
    }

    private companion object {
        const val EXPIRY_POLLS = 15
        val RELOAD_CODES = setOf("VERSION_CONFLICT", "CLOCK_EXPIRED", "GAME_FINISHED")
    }
}

/** Configuración de una partida nueva (pestaña Jugar). */
data class NewGameUi(
    val minutes: Int? = null,
    val creating: Boolean = false,
    val error: String? = null,
    /** gameId recién creado: la pantalla navega a la partida y lo consume. */
    val created: String? = null,
)

class NewGameViewModel(private val repo: GameRepository) : ViewModel() {
    private val _ui = MutableStateFlow(NewGameUi())
    val ui: StateFlow<NewGameUi> = _ui.asStateFlow()

    fun setMinutes(minutes: Int?) = _ui.update { it.copy(minutes = minutes, error = null) }

    fun create() {
        if (_ui.value.creating) return
        _ui.update { it.copy(creating = true, error = null) }
        viewModelScope.launch {
            repo.createLocal(_ui.value.minutes)
                .onSuccess { game -> _ui.update { it.copy(creating = false, created = game.gameId) } }
                .onFailure { e -> _ui.update { it.copy(creating = false, error = e.userMessage()) } }
        }
    }

    fun consumeCreated() = _ui.update { it.copy(created = null) }
}
