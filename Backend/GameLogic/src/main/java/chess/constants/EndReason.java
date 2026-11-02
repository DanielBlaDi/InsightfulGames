package chess.constants;

public enum EndReason{
    CHECKMATE(),
    STALEMATE(),
    SURRENDER(),
    DRAW(),
    TIMEOUT(),
    ABANDONMENT(),
    EXPIRED();

    public static int size(){
        return EndReason.values().length;
    }

    public static String allPossibleEndReasons(){
        String result = "\"";

        for(int i=0; i<EndReason.values().length-1; i++){
            result += EndReason.values()[i] + "\" | \"";
        }

        return result + EndReason.values()[EndReason.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case CHECKMATE:
                return "checkmate";
            case STALEMATE:
                return "stalemate";
            case SURRENDER:
                return "surrender";
            case DRAW:
                return "draw";
            case TIMEOUT:
                return "timeout";
            case ABANDONMENT:
                return "abandonment";
            case EXPIRED:
                return "expired";
            default:
                return null;
        }
    }
}