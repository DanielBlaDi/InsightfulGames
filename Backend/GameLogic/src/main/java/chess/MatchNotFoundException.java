package chess;

public class MatchNotFoundException extends RuntimeException{
	MatchNotFoundException(String id) {
		super("Could not find match " + id);
	}
}