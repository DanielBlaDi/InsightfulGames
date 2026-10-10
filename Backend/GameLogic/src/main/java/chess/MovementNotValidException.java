package chess;

public class MovementNotValidException extends RuntimeException{
	MovementNotValidException(String boardFenBeforeMove, String coordinateNotation){
		super("Move \"" + coordinateNotation + "\" is not valid for board state \"" + boardFenBeforeMove + "\"");
	}
}