package chess.matches;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Errores de petición: 400 VALIDATION_ERROR para peticiones mal formadas. */
@RestControllerAdvice
public class RequestNotValidAdvice{
	@ExceptionHandler(RequestNotValidException.class)
	@ResponseStatus(HttpStatus.BAD_REQUEST)
	Map<String, Object> requestNotValidHandler(RequestNotValidException exception){
		return error("VALIDATION_ERROR", exception.getMessage());
	}

	/** Cuerpo ausente o que no es JSON. */
	@ExceptionHandler(HttpMessageNotReadableException.class)
	@ResponseStatus(HttpStatus.BAD_REQUEST)
	Map<String, Object> bodyNotReadableHandler(HttpMessageNotReadableException exception){
		return error("VALIDATION_ERROR", "El cuerpo de la petición no es un JSON válido");
	}

	private static Map<String, Object> error(String code, String message){
		return Map.of("error", Map.of("code", code, "message", message));
	}
}
