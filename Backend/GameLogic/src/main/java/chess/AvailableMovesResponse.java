package chess;

import java.util.List;

/** JSON response for PATCH /movements/{coordinate}/*/
public record AvailableMovesResponse(List<String> availableDestinationCoordinates){
    public static AvailableMovesResponse of(List<String> availableDestinationCoordinates){
        return new AvailableMovesResponse(availableDestinationCoordinates);
    }
}