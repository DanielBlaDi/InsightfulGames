package chess.constants;

public enum Color{
    WHITE(),
    BLACK();

    public static int size(){
        return Color.values().length;
    }

    public static String allPossibleColors(){
        String result = "\"";

        for(int i=0; i<Color.values().length-1; i++){
            result += Color.values()[i] + "\" | \"";
        }

        return result + Color.values()[Color.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case WHITE:
                return "white";
            case BLACK:
                return "black";
            default:
                return null;
        }
    }
}