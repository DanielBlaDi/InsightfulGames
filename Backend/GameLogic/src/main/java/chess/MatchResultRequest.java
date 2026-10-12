package chess;

/** Cuerpo de PATCH /matches/{id}/result: result = WHITE_WINS | BLACK_WINS | DRAW. */
public record MatchResultRequest(String result, String reason){
}