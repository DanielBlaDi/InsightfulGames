package chess;

import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Side;

/** Respuesta JSON de PATCH /matches/{id}/movements */
public record MovementResponse(String updatedFen, String turn, String outcome, String reason){

    public static MovementResponse of(Board board){
        String turn = board.getSideToMove() == Side.WHITE ? "WHITE" : "BLACK";
        String outcome = "IN_PROGRESS";
        String reason = "IN_PROGRESS";

        if(board.isMated()){
            //Quien tiene el turno es quien quedó en jaque mate
            outcome = board.getSideToMove() == Side.WHITE ? "BLACK_WINS" : "WHITE_WINS";
            reason = "CHECKMATE";
        }else if(board.isStaleMate()){
            outcome = "DRAW";
            reason = "STALEMATE";
        }else if(board.isDraw()){
            outcome = "DRAW";
            reason = "DRAW_RULE";
        }

        return new MovementResponse(board.getFen(), turn, outcome, reason);
    }
}
