package chess.matches;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CannotJoinMatchAdvice{
	@ExceptionHandler(CannotJoinMatchException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> matchNotFoundHandler(CannotJoinMatchException exception){
		return Map.of("error", Map.of("code", exception.getErrorCode(), "message", exception.getMessage()));
	}
}
