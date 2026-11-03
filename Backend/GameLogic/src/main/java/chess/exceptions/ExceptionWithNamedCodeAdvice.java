package chess.exceptions;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Advice class for all custom exceptions of this component. Gives errors the correct format */
@RestControllerAdvice
public class ExceptionWithNamedCodeAdvice{
	@ExceptionHandler(RequestNotValidException.class)
	@ResponseStatus(HttpStatus.BAD_REQUEST)
	Map<String, Object> requestNotValidHandler(RequestNotValidException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	/** Cuerpo ausente o que no es JSON. */
	@ExceptionHandler(HttpMessageNotReadableException.class)
	@ResponseStatus(HttpStatus.BAD_REQUEST)
	Map<String, Object> bodyNotReadableHandler(HttpMessageNotReadableException exception){
		return error("VALIDATION_ERROR", "El cuerpo de la petición no es un JSON válido");
	}

	@ExceptionHandler(MatchNotFoundException.class)
	@ResponseStatus(HttpStatus.NOT_FOUND)
	Map<String, Object> matchNotFoundHandler(MatchNotFoundException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(MatchNotFinishedException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> matchNotFinishedHandler(MatchNotFinishedException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(MatchNotInProgressException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> matchNotInProgressHandler(MatchNotInProgressException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(CannotReplyToDrawException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> drawExceptionHandler(CannotReplyToDrawException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(CannotOfferDrawException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> drawExceptionHandler(CannotOfferDrawException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(MovementNotValidException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> movementNotValidHandler(MovementNotValidException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(ParticipantsInvalidException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> participantsInvalidHandler(ParticipantsInvalidException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(CannotJoinMatchException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> cannotJoinMatchHandler(CannotJoinMatchException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(VersionConflictException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> versionConflictHandler(VersionConflictException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(CreationKeyException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> creationKeyHandler(CreationKeyException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	private static Map<String, Object> error(String code, String message){
		return Map.of("error", Map.of("code", code, "message", message));
	}
}
