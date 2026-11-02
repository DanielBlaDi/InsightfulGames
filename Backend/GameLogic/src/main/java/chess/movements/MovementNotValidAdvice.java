package chess.movements;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Errores de petición: 422 para jugadas que no se aceptan*/
@RestControllerAdvice
public class MovementNotValidAdvice{
	@ExceptionHandler(MovementNotValidException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> movementNotValidHandler(MovementNotValidException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	private static Map<String, Object> error(String code, String message){
		return Map.of("error", Map.of("code", code, "message", message));
	}
}
