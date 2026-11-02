package chess.matches;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DrawExceptionAdvice{
	@ExceptionHandler(DrawNotOfferedException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> drawExceptionHandler(DrawNotOfferedException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	@ExceptionHandler(CannotOfferDrawException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> drawExceptionHandler(CannotOfferDrawException exception){
		return error(exception.getCode(), exception.getMessage());
	}

	private static Map<String, Object> error(String code, String message){
		return Map.of("error", Map.of("code", code, "message", message));
	}
}
