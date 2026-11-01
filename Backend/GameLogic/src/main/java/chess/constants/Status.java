package chess.constants;

public enum Status{
    IN_PROGRESS(),
    FINISHED(),
    WAITING();

    public static int size(){
        return Status.values().length;
    }

    public static String allPossibleStatuses(){
        String result = "\"";

        for(int i=0; i<Status.values().length-1; i++){
            result += Status.values()[i] + "\" | \"";
        }

        return result + Status.values()[Status.values().length-1] + "\"";
    }

    @Override public String toString(){
        switch(this){
            case IN_PROGRESS:
                return "in_progress";
            case FINISHED:
                return "finished";
            case WAITING:
                return "waiting";
            default:
                return null;
        }
    }
}