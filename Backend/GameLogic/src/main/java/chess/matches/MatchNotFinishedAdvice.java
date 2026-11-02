package chess.matches;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class MatchNotFinishedAdvice{
	@ExceptionHandler(MatchNotFinishedException.class)
	@ResponseStatus(HttpStatus.CONFLICT)
	Map<String, Object> matchNotFinishedHandler(MatchNotFinishedException exception){
		return Map.of("error", Map.of("code", exception.getCode(), "message", exception.getMessage()));
	}
}
