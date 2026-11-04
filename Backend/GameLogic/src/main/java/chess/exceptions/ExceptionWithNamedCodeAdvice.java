package chess.exceptions;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Advice class for all custom exceptions of this component. Gives errors the correct format */
@RestControllerAdvice
public class ExceptionWithNamedCodeAdvice{
	private static final Logger log = LoggerFactory.getLogger(ExceptionWithNamedCodeAdvice.class);

	@ExceptionHandler(GameFinishedException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> gameFinishedHandler(GameFinishedException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	/** Parámetros de query ausentes o con tipo inválido, o cuerpo que no es JSON. */
	@ExceptionHandler({MissingServletRequestParameterException.class, MethodArgumentTypeMismatchException.class, HttpMediaTypeNotSupportedException.class})
	@ResponseStatus(HttpStatus.BAD_REQUEST)
	Map<String, Object> badRequestHandler(Exception exception){
		return error(RequestNotValidException.VALIDATION_ERROR, "La petición no es válida: " + exception.getMessage());
	}

	@ExceptionHandler({NoResourceFoundException.class, HttpRequestMethodNotSupportedException.class})
	@ResponseStatus(HttpStatus.NOT_FOUND)
	Map<String, Object> routeNotFoundHandler(Exception exception){
		return error("NOT_FOUND", "Ruta inexistente");
	}

	/** Cualquier otro error: 500 INTERNAL_ERROR con la forma del contrato, y su traza en el log. */
	@ExceptionHandler(Exception.class)
	ResponseEntity<Map<String, Object>> unexpectedHandler(Exception exception){
		log.error("Error inesperado", exception);
		return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error("INTERNAL_ERROR", "Error interno del servidor"));
	}
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

	@ExceptionHandler(ClockException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> clockExceptionHandler(ClockException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	private static Map<String, Object> error(String code, String message){
		return Map.of("error", Map.of("code", code, "message", message));
	}
}
