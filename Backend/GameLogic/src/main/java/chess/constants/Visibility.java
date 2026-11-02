package chess.constants;

public enum Visibility{
    PRIVATE(),
    SHARED();

    public static int size(){
        return Visibility.values().length;
    }

    public static String allPossibleVisibilities(){
        String result = "\"";

        for(int i=0; i<Visibility.values().length-1; i++){
            result += Visibility.values()[i] + "\" | \"";
        }

        return result + Visibility.values()[Visibility.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case PRIVATE:
                return "private";
            case SHARED:
                return "shared";
            default:
                return null;
        }
    }
}