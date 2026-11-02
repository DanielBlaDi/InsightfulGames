package chess.constants;

public enum Mode{
    LOCAL(),
    VS_BOT(),
    MULTIPLAYER();

    public static int size(){
        return Mode.values().length;
    }

    public static String allPossibleModes(){
        String result = "\"";

        for(int i=0; i<Mode.values().length-1; i++){
            result += Mode.values()[i] + "\" | \"";
        }

        return result + Mode.values()[Mode.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case LOCAL:
                return "local";
            case VS_BOT:
                return "vs_bot";
            case MULTIPLAYER:
                return "multiplayer";
            default:
                return null;
        }
    }
}