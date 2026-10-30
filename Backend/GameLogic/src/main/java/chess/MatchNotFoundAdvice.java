package chess;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class MatchNotFoundAdvice{
	@ExceptionHandler(MatchNotFoundException.class)
	@ResponseStatus(HttpStatus.NOT_FOUND)
	Map<String, Object> matchNotFoundHandler(MatchNotFoundException exception){
		return Map.of("error", Map.of("code", "GAME_NOT_FOUND", "message", exception.getMessage()));
	}
}
