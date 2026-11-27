package chess.constants;

public enum Result{
    DRAW();

    public static int size(){
        return Result.values().length + Color.values().length;
    }

    public static String allPossibleResults(){
        String result = "\"";

        for(int i=0; i<Color.values().length; i++){
            result += Color.values()[i] + "\" | \"";
        }

        for(int i=0; i<Result.values().length-1; i++){
            result += Result.values()[i] + "\" | \"";
        }

        return result + Result.values()[Result.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case DRAW:
                return "draw";
            default:
                return null;
        }
    }
}