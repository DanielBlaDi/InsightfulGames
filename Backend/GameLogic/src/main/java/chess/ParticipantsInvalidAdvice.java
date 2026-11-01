package chess;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ParticipantsInvalidAdvice{
	@ExceptionHandler(ParticipantsInvalidException.class)
	@ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
	Map<String, Object> participantsInvalidHandler(ParticipantsInvalidException exception){
		return Map.of("error", Map.of("code", "PARTICIPANTS_INVALID", "message", exception.getMessage()));
	}
}
