package chess.exceptions;

import chess.constants.Status;

/**
 * Http 422 For clock and timer related errors
 */
public class ClockException extends ExceptionWithNamedCode{
	public static final String CLOCK_EXPIRED = "CLOCK_EXPIRED";
	public static final String CLOCK_NOT_EXPIRED = "CLOCK_NOT_EXPIRED";
	public static final String WAITING_NOT_EXPIRED = "WAITING_NOT_EXPIRED";

	private ClockException(String code, String message){
		super(code, message);
	}

	public static ClockException timedOut(){
		return new ClockException(CLOCK_EXPIRED, "El reloj expiró");
	}

	public static ClockException notTimedOut(){
		return new ClockException(CLOCK_NOT_EXPIRED, "El reloj no ha expirado todavía");
	}

	public static ClockException waitingNotExpired(){
		return new ClockException(WAITING_NOT_EXPIRED, "La partida en " + Status.WAITING + " no ha expirado todavía");
	}
}
