package worker;

/** Forma común de error del contrato (4.1): { "error": { "code", "message" } }. */
public record ErrorResponse(Detail error){

    public record Detail(String code, String message){}
}
