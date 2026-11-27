package chess.exceptions;

/** HTTP 409 When trying to modify a match with a wrong version*/
public class VersionConflictException extends ExceptionWithNamedCode{
    public static final String VERSION_CONFLICT = "VERSION_CONFLICT";

    private VersionConflictException(String code, String message){
        super(code, message);
    }

    public static VersionConflictException versionConflict(){
		return new VersionConflictException(VERSION_CONFLICT, "La versión esperada no concuerda con la versión del sistema");
	}
}